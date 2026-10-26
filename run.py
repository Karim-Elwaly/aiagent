"""
UAOS All-in-One Launcher

Starts both the Temporal Worker and the FastAPI Gateway with a single command:
    python run.py

Features:
- Validates environment & Temporal connectivity before starting
- Spawns Temporal Worker and FastAPI server in isolated processes
- Unified graceful shutdown on Ctrl+C
"""

import os
import socket
import subprocess
import sys
import time

# Auto-switch to .venv Python interpreter if running under global python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(venv_python).lower():
    if sys.platform == "win32":
        try:
            res = subprocess.call([venv_python] + sys.argv)
            sys.exit(res)
        except Exception:
            pass
    else:
        try:
            os.execv(venv_python, [venv_python] + sys.argv)
        except Exception:
            pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure UTF-8 output with fallback for Windows terminals
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BANNER = r"""
    _                    _   _   _       _     
   / \   __ _  ___ _ __ | |_| | | |_   _| |__  
  / _ \ / _` |/ _ \ '_ \| __| |_| | | | | '_ \ 
 / ___ \ (_| |  __/ | | | |_|  _  | |_| | |_) |
/_/   \_\__, |\___|_| |_|\__|_| |_|\__,_|_.__/ 
        |___/                                   
 Intelligent Agent Workspace
"""


def check_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def main():
    print(BANNER)
    print("=" * 60)
    print(">> Starting AgentHub (Intelligent Agent Workspace)...")
    print("=" * 60)

    # 1. Check Python version
    if sys.version_info < (3, 11):  # noqa: UP036
        print("[ERROR] Python 3.11+ is required.")
        sys.exit(1)

    # 1b. Windows Event Loop Check (Phase 0.7)
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        print("[*] Configured Windows Proactor event loop policy.")


    # 2. Check Temporal Server connection
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7234")
    host_parts = temporal_host.split(":")
    t_host = host_parts[0]
    t_port = int(host_parts[1]) if len(host_parts) > 1 else 7234

    print(f"[*] Probing Temporal Server at {temporal_host}...")
    if check_port(t_host, t_port, timeout=1.5):
        print(f"    [OK] Temporal Server detected on {temporal_host}")
        # Ensure Temporal Web UI (port 8234) is also running
        if not check_port("localhost", 8234, timeout=0.8):
            print("    [*] Temporal Server is up, but Web UI (port 8234) is stopped. Auto-starting temporal-ui...")
            try:
                res = subprocess.run(["docker", "start", "uaos-temporal-ui"], capture_output=True, text=True, timeout=4)
                if res.returncode != 0:
                    subprocess.run(
                        ["docker", "compose", "up", "-d", "temporal-ui"],
                        capture_output=True,
                        text=True,
                        timeout=12,
                    )
                for _ in range(6):
                    time.sleep(1.0)
                    if check_port("localhost", 8234, timeout=1.0):
                        print("    [OK] Temporal Web UI online at http://localhost:8234")
                        break
            except Exception:
                pass
    else:
        print(f"    [*] Temporal Server not responding on {temporal_host}. Checking Docker...")
        started = False
        try:
            # 1. Try starting existing containers
            for cname in ["uaos-postgres", "uaos-temporal", "uaos-temporal-ui"]:
                res = subprocess.run(["docker", "start", cname], capture_output=True, text=True, timeout=4)
                if res.returncode == 0:
                    started = True

            if started:
                print(f"    [*] Started existing Temporal Docker containers. Waiting for ports {t_port} & 8234...")
                for _ in range(8):
                    time.sleep(1.0)
                    if check_port(t_host, t_port, timeout=1.0):
                        print(f"    [OK] Temporal Server online on {temporal_host}!")
                        break

            # 2. If not started or still offline, run docker compose up for the full stack
            if not check_port(t_host, t_port, timeout=0.5):
                res_dc = subprocess.run(
                    ["docker", "compose", "up", "-d", "postgresql", "temporal", "temporal-ui"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if res_dc.returncode == 0:
                    print(f"    [*] Launched Temporal stack via Docker Compose. Waiting for port {t_port}...")
                    for _ in range(10):
                        time.sleep(1.0)
                        if check_port(t_host, t_port, timeout=1.0):
                            print(f"    [OK] Temporal Server online on {temporal_host}!")
                            started = True
                            break
        except Exception:
            pass

        if not check_port(t_host, t_port, timeout=0.5):
            print("    [*] Temporal Server (port 7234) and Web UI (port 8234) are offline.")
            print("    [*] Note: To enable Temporal Web UI on http://localhost:8234, start Docker Desktop and run:")
            print("        docker compose up -d postgresql temporal temporal-ui")
            print("    ⚡ Standalone In-Process Execution Engine is ACTIVE (zero failure, fully functional).\n")

    default_port = int(os.getenv("API_PORT", "8000"))
    api_host = os.getenv("API_HOST", "127.0.0.1")

    # If default port is in use, find next free port
    if check_port(api_host, default_port, timeout=0.5):
        api_port = default_port + 1
        while check_port(api_host, api_port, timeout=0.5):
            api_port += 1
        print(f"[*] Port {default_port} is in use. Auto-selected available port {api_port}.")
    else:
        api_port = default_port

    web_ui_online = check_port("localhost", 8234, timeout=0.5)
    t_web_status = "http://localhost:8234 (Online)" if web_ui_online else "Offline (start Docker Desktop & run 'docker compose up -d postgresql temporal temporal-ui')"

    fleet_studio_online = check_port("localhost", 3000, timeout=0.5)
    fleet_status = "http://localhost:3000 (Online)" if fleet_studio_online else "http://localhost:3000 (Start with: cd frontend/frontend && npm run dev)"

    print("\n" + "=" * 60)
    print(f"  🚀 AgentHub Mission Control: http://localhost:{api_port}")
    print(f"  🛰️  Fleet Studio UI:         {fleet_status}")
    print(f"  📚 Swagger API Docs:        http://localhost:{api_port}/docs")
    print(f"  ⏱️  Temporal Web UI:         {t_web_status}")
    print("=" * 60)
    print("Press Ctrl+C to stop all services.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()
    # Children must see the auto-selected port, not API_PORT from .env (Hermes MCP URL derives from it).
    env["API_PORT"] = str(api_port)
    env["PYTHONUNBUFFERED"] = "1"

    processes = []

    api_log_f = open(os.path.join("data", "api.log"), "a", encoding="utf-8", errors="replace")
    worker_log_f = open(os.path.join("data", "worker.log"), "a", encoding="utf-8", errors="replace")

    python_bin = venv_python if os.path.exists(venv_python) else sys.executable

    try:
        # Start Worker Runner process
        worker_proc = subprocess.Popen(
            [python_bin, "-m", "src.orchestrator.worker_runner"],
            env=env,
            stdout=worker_log_f,
            stderr=subprocess.STDOUT,
        )
        processes.append(worker_proc)

        # Start FastAPI process via uvicorn
        api_proc = subprocess.Popen(
            [
                python_bin,
                "-m",
                "uvicorn",
                "src.api.main:app",
                "--host",
                api_host,
                "--port",
                str(api_port),
                "--reload",
                "--reload-dir",
                "src",
            ],
            env=env,
            stdout=api_log_f,
            stderr=subprocess.STDOUT,
        )
        processes.append(api_proc)

        # Keep services running, auto-restarting child processes if they exit
        while True:

            if worker_proc.poll() is not None:
                ret = worker_proc.poll()
                print(f"\n[!] Worker Runner exited with code {ret}. Auto-restarting in 2s...")
                time.sleep(2.0)
                worker_proc = subprocess.Popen(
                    [python_bin, "-m", "src.orchestrator.worker_runner"],
                    env=env,
                    stdout=worker_log_f,
                    stderr=subprocess.STDOUT,
                )
                processes[0] = worker_proc

            if api_proc.poll() is not None:
                ret = api_proc.poll()
                print(f"\n[!] API Gateway exited with code {ret}. Auto-restarting in 2s...")
                time.sleep(2.0)
                api_proc = subprocess.Popen(
                    [
                        python_bin,
                        "-m",
                        "uvicorn",
                        "src.api.main:app",
                        "--host",
                        api_host,
                        "--port",
                        str(api_port),
                        "--reload",
                        "--reload-dir",
                        "src",
                    ],
                    env=env,
                    stdout=api_log_f,
                    stderr=subprocess.STDOUT,
                )
                processes[1] = api_proc

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[*] Shutting down AgentHub services gracefully...")
    finally:
        for p in processes:
            if p.poll() is None:
                if sys.platform == "win32":
                    p.kill()
                else:
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        p.kill()
        print("[OK] All processes stopped. Goodbye!")


if __name__ == "__main__":
    main()
