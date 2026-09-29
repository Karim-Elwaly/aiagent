"""
Unit Tests for Enterprise Security Connectors Framework

Validates that all 13 connectors initialize, execute health checks,
export valid ToolSpecs with accurate RiskLevels, and register into ToolRegistry.
"""

import json
import pytest

from src.connectors.base import ConnectorCategory, ConnectorStatus
from src.connectors.manager import ConnectorManager
from src.core.models import RiskLevel
from src.registry.tool_registry import ToolRegistry


@pytest.mark.asyncio
async def test_all_connectors_initialization_and_tool_export():
    """Verify that all 13 enterprise security connectors load, export tools, and register."""
    registry = ToolRegistry()
    manager = ConnectorManager()
    await manager.initialize(registry=registry)

    connectors = manager.list_connectors(mask_secrets=True)
    assert len(connectors) == 13, f"Expected 13 connectors, found {len(connectors)}"

    # Check presence of key enterprise platforms
    connector_ids = {c["connector_id"] for c in connectors}
    expected_ids = {
        "elasticsearch",
        "crowdstrike",
        "splunk",
        "sentinel",
        "defender",
        "sentinelone",
        "paloalto",
        "fortigate",
        "okta",
        "entra_id",
        "virustotal",
        "abuseipdb",
        "thehive",
    }
    assert expected_ids.issubset(connector_ids), f"Missing connectors: {expected_ids - connector_ids}"

    # Verify each category is represented
    categories = {c["category"] for c in connectors}
    assert "siem" in categories
    assert "edr" in categories
    assert "firewall" in categories
    assert "iam" in categories
    assert "threat_intel" in categories
    assert "itsm" in categories


@pytest.mark.asyncio
async def test_connector_connection_tests():
    """Verify that test_connection succeeds for each connector in simulation/sandbox mode."""
    manager = ConnectorManager()
    await manager.initialize()

    for conn_info in manager.list_connectors():
        cid = conn_info["connector_id"]
        success, message, latency = await manager.test_connector(cid)
        assert success is True, f"test_connection failed for connector {cid}: {message}"
        assert latency >= 0.0
        assert "Simulation Mode" in message or "Connected" in message


@pytest.mark.asyncio
async def test_risk_level_governance():
    """Ensure all destructive containment tools are HIGH risk and read-only tools are LOW risk."""
    registry = ToolRegistry()
    manager = ConnectorManager()
    await manager.initialize(registry=registry)

    # 1. High-Risk Containment Actions (Must trigger human approval gate)
    high_risk_tools = [
        "crowdstrike_contain_host",
        "crowdstrike_lift_containment",
        "defender_isolate_machine",
        "sentinelone_quarantine_agent",
        "paloalto_register_ip_dag",
        "paloalto_unregister_ip_dag",
        "fortigate_ban_ip",
        "fortigate_unban_ip",
        "okta_clear_user_sessions",
        "okta_suspend_user",
        "entraid_revoke_sessions",
        "entraid_disable_account",
    ]
    for tool_name in high_risk_tools:
        tool = registry.get_tool_by_name(tool_name)
        assert tool is not None, f"Tool '{tool_name}' not registered"
        assert tool.risk_level == RiskLevel.HIGH, f"Tool '{tool_name}' should be RiskLevel.HIGH, got {tool.risk_level}"

    # 2. Low-Risk Query Actions
    low_risk_tools = [
        "elastic_search_logs",
        "elastic_lookup_ioc",
        "crowdstrike_get_device",
        "splunk_search_spl",
        "sentinel_query_kql",
        "defender_get_machine",
        "sentinelone_find_agent",
        "okta_get_user",
        "entraid_get_user",
        "virustotal_lookup_ip",
        "virustotal_lookup_hash",
        "abuseipdb_check_ip",
    ]
    for tool_name in low_risk_tools:
        tool = registry.get_tool_by_name(tool_name)
        assert tool is not None, f"Tool '{tool_name}' not registered"
        assert tool.risk_level == RiskLevel.LOW, f"Tool '{tool_name}' should be RiskLevel.LOW, got {tool.risk_level}"


@pytest.mark.asyncio
async def test_simulated_execution_payloads():
    """Verify that calling connector tools in simulation returns valid JSON with realistic forensic attributes."""
    manager = ConnectorManager()
    await manager.initialize()

    # 1. Elasticsearch SIEM Log Search
    es = manager.get_connector("elasticsearch")
    res_str = await es.search_logs(query="event.action: blocked")
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert len(res["hits"]) > 0
    assert "Log4j" in res_str or "denied" in res_str.lower()

    # 2. CrowdStrike Host Containment
    cs = manager.get_connector("crowdstrike")
    res_str = await cs.contain_host(aid="4b98fa32ec114889b932c0993081eac1", justification="Active C2 beaconing")
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["action"] == "contain"
    assert "network-isolated" in res["message"]

    # 3. Palo Alto DAG Blacklisting
    pa = manager.get_connector("paloalto")
    res_str = await pa.register_ip_dag(ip_address="198.51.100.220", tag="block_adversary_ioc")
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert "Dynamic Address Group" in res["message"]

    # 4. Okta Session Invalidation
    okta = manager.get_connector("okta")
    res_str = await okta.clear_user_sessions(user_id="user_123", justification="Compromised credentials")
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert "invalidated" in res["message"]

    # 5. VirusTotal CTI Lookup
    vt = manager.get_connector("virustotal")
    res_str = await vt.lookup_ip(ip_address="198.51.100.220")
    res = json.loads(res_str)
    assert res["status"] == "success"
    assert res["verdict"] == "MALICIOUS"
    assert res["malicious_votes"] > 50
