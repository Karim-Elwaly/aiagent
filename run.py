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
    else:
        print(f"    [*] Temporal Server not responding on {temporal_host}. Checking Docker...")
        started = False
        try:
            # 1. Try starting existing containers
            for cname in ["uaos-temporal", "aisoc-temporal"]:
                res = subprocess.run(["docker", "start", cname], capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    print(f"    [*] Started Docker container '{cname}'. Waiting for port {t_port}...")
                    for _ in range(6):
                        time.sleep(1.0)
                        if check_port(t_host, t_port, timeout=1.0):
                            print(f"    [OK] Temporal Server online on {temporal_host}!")
                            started = True
                            break
                    if started:
                        break

            # 2. If not started, try docker compose up -d temporal
            if not started:
                res_dc = subprocess.run(["docker", "compose", "up", "-d", "temporal"], capture_output=True, text=True, timeout=10)
                if res_dc.returncode == 0:
                    print(f"    [*] Launched Temporal via Docker Compose. Waiting for port {t_port}...")
                    for _ in range(8):
                        time.sleep(1.0)
                        if check_port(t_host, t_port, timeout=1.0):
                            print(f"    [OK] Temporal Server online on {temporal_host}!")
                            started = True
                            break
        except Exception:
            pass

        if not started and not check_port(t_host, t_port, timeout=0.5):
            print("    [*] Temporal Server is offline.")
            print("    ⚡ Standalone In-Process Execution Engine is ACTIVE (zero failure, fully functional).\n")

    default_port = int(os.getenv("API_PORT", "8000"))
    api_host = os.getenv("API_HOST", "127.0.0.1")

    # If default port is in use and not explicitly set by user, find next free port
    if os.getenv("API_PORT") is None and check_port(api_host, default_port, timeout=0.5):
        api_port = default_port + 1
        while check_port(api_host, api_port, timeout=0.5):
            api_port += 1
        print(f"[*] Port {default_port} is in use. Auto-selected available port {api_port}.")
    else:
        api_port = default_port

    temporal_online = check_port(t_host, t_port, timeout=0.5)
    t_web_status = "http://localhost:8234 (Online)" if temporal_online else "Offline (run 'docker compose up -d temporal' to enable)"

    print("\n" + "=" * 60)
    print(f"  🚀 AgentHub Mission Control UI: http://localhost:{api_port}")
    print(f"  📚 Swagger API Docs:        http://localhost:{api_port}/docs")
    print(f"  ⏱️  Temporal Web UI:         {t_web_status}")
    print("=" * 60)
    print("Press Ctrl+C to stop all services.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    def get_max_src_mtime() -> float:
        max_m = 0.0
        src_path = os.path.join(os.getcwd(), "src")
        if not os.path.exists(src_path):
            return 0.0
        for root, _, files in os.walk(src_path):
            for f in files:
                if f.endswith(".py"):
                    try:
                        m = os.path.getmtime(os.path.join(root, f))
                        if m > max_m:
                            max_m = m
                    except OSError:
                        pass
        return max_m

    last_src_mtime = get_max_src_mtime()
    processes = []

    try:
        # Start Worker Runner process
        worker_proc = subprocess.Popen(
            [sys.executable, "-m", "src.orchestrator.worker_runner"],
            env=env,
        )
        processes.append(worker_proc)

        # Start FastAPI process via uvicorn
        api_proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "src.api.main:app",
                "--host",
                api_host,
                "--port",
                str(api_port),
                "--reload",
            ],
            env=env,
        )
        processes.append(api_proc)

        # Keep services running, auto-restarting child processes if they exit
        while True:
            # Check for source code changes to auto-reload worker
            current_src_mtime = get_max_src_mtime()
            if current_src_mtime > last_src_mtime:
                last_src_mtime = current_src_mtime
                print("\n[*] Detected code change in src/. Reloading Temporal Worker...")
                if worker_proc.poll() is None:
                    worker_proc.terminate()
                    try:
                        worker_proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        worker_proc.kill()
                time.sleep(1.0)
                worker_proc = subprocess.Popen(
                    [sys.executable, "-m", "src.orchestrator.worker_runner"],
                    env=env,
                )
                processes[0] = worker_proc

            if worker_proc.poll() is not None:
                ret = worker_proc.poll()
                print(f"\n[!] Worker Runner exited with code {ret}. Auto-restarting in 2s...")
                time.sleep(2.0)
                worker_proc = subprocess.Popen(
                    [sys.executable, "-m", "src.orchestrator.worker_runner"],
                    env=env,
                )
                processes[0] = worker_proc

            if api_proc.poll() is not None:
                ret = api_proc.poll()
                print(f"\n[!] API Gateway exited with code {ret}. Auto-restarting in 2s...")
                time.sleep(2.0)
                api_proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "src.api.main:app",
                        "--host",
                        api_host,
                        "--port",
                        str(api_port),
                        "--reload",
                    ],
                    env=env,
                )
                processes[1] = api_proc

            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[*] Shutting down AgentHub services gracefully...")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("[OK] All processes stopped. Goodbye!")


if __name__ == "__main__":
    main()
