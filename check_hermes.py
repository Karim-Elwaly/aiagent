import os
import json
import yaml
from pathlib import Path
import httpx

hermes_home = Path(os.path.expanduser(r"~\AppData\Local\hermes"))
profiles_dir = hermes_home / "profiles"

print("Checking Hermes profiles in:", profiles_dir)

# 1. Check data/hermes/profiles.json
local_profiles_file = Path("data/hermes/profiles.json")
if local_profiles_file.exists():
    try:
        data = json.loads(local_profiles_file.read_text(encoding="utf-8"))
        print("\ndata/hermes/profiles.json:")
        for name, pdata in data.items():
            if "dyn" in name or name in ["default", "aiagent-default", "aiagent-orchestrator", "aiagent-soc-investigator"]:
                print(f"  {name}: mcp_url={pdata.get('mcp_url')} mcp_listed_at={pdata.get('mcp_listed_at')}")
    except Exception as e:
        print("Error reading data/hermes/profiles.json:", e)

# 2. Check aiagent-dyn-145d1c8f specifically
p_145 = profiles_dir / "aiagent-dyn-145d1c8f"
print(f"\nProfile {p_145.name} exists: {p_145.is_dir()}")
if p_145.is_dir():
    cfg_file = p_145 / "config.yaml"
    env_file = p_145 / ".env"
    print(f"  config.yaml exists: {cfg_file.is_file()}")
    if cfg_file.is_file():
        print("  config.yaml contents:\n", cfg_file.read_text(encoding="utf-8"))
    print(f"  .env exists: {env_file.is_file()}")
    if env_file.is_file():
        print("  .env contents:\n", env_file.read_text(encoding="utf-8"))

# 3. Check all profiles for mcp_servers.aiagent.url
print("\nScanning all profiles config.yaml for mcp_servers.aiagent:")
for p in sorted(profiles_dir.iterdir()):
    if p.is_dir():
        cfg = p / "config.yaml"
        if cfg.is_file():
            try:
                y = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                mcp = y.get("mcp_servers", {}).get("aiagent")
                if mcp:
                    url = mcp.get("url")
                    print(f"  {p.name}: url={url}")
            except Exception as e:
                print(f"  {p.name}: error {e}")

# 4. Test MCP endpoint directly via httpx
print("\nTesting MCP endpoint at http://127.0.0.1:8000/mcp/:")
try:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=2.0)
    print("  GET /health:", r.status_code, r.text[:100])
except Exception as e:
    print("  GET /health failed:", e)

# Read token for dyn profile or default
token = None
if p_145.is_dir() and (p_145 / ".env").is_file():
    for line in (p_145 / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("AIAGENT_MCP_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
print(f"  Token for aiagent-dyn-145d1c8f: {token}")

if token:
    try:
        r = httpx.post(
            "http://127.0.0.1:8000/mcp/",
            headers={"Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            timeout=5.0,
        )
        print("  POST /mcp/ tools/list status:", r.status_code)
        print("  POST /mcp/ tools/list response:", r.text[:300])
    except Exception as e:
        print("  POST /mcp/ failed:", e)
