"""
Enterprise Security Connector Implementations Registry
"""

from src.connectors.implementations.abuseipdb import AbuseIPDBConnector
from src.connectors.implementations.crowdstrike import CrowdStrikeFalconConnector
from src.connectors.implementations.defender import MicrosoftDefenderConnector
from src.connectors.implementations.elasticsearch import ElasticsearchConnector
from src.connectors.implementations.entra_id import EntraIdConnector
from src.connectors.implementations.fortigate import FortiGateConnector
from src.connectors.implementations.okta import OktaConnector
from src.connectors.implementations.palo_alto import PaloAltoConnector
from src.connectors.implementations.sentinel import MicrosoftSentinelConnector
from src.connectors.implementations.sentinelone import SentinelOneConnector
from src.connectors.implementations.splunk import SplunkConnector
from src.connectors.implementations.thehive import TheHiveConnector
from src.connectors.implementations.virustotal import VirusTotalConnector

ALL_CONNECTOR_CLASSES = [
    ElasticsearchConnector,
    CrowdStrikeFalconConnector,
    SplunkConnector,
    MicrosoftSentinelConnector,
    MicrosoftDefenderConnector,
    SentinelOneConnector,
    PaloAltoConnector,
    FortiGateConnector,
    OktaConnector,
    EntraIdConnector,
    VirusTotalConnector,
    AbuseIPDBConnector,
    TheHiveConnector,
]

__all__ = [
    "ALL_CONNECTOR_CLASSES",
    "ElasticsearchConnector",
    "CrowdStrikeFalconConnector",
    "SplunkConnector",
    "MicrosoftSentinelConnector",
    "MicrosoftDefenderConnector",
    "SentinelOneConnector",
    "PaloAltoConnector",
    "FortiGateConnector",
    "OktaConnector",
    "EntraIdConnector",
    "VirusTotalConnector",
    "AbuseIPDBConnector",
    "TheHiveConnector",
]
