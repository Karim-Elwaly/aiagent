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
  _   _    _    ___  ____  
 | | | |  / \  / _ \/ ___| 
 | | | | / _ \| | | \___ \ 
 | |_| |/ ___ \ |_| |___) |
  \___//_/   \_\___/|____/ 
 Universal Agent Orchestration System
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
    print(">> Starting UAOS (Universal Agent Orchestration System)...")
    print("=" * 60)

    # 1. Check Python version
    if sys.version_info < (3, 11):  # noqa: UP036
        print("[ERROR] Python 3.11+ is required.")
        sys.exit(1)

    # 2. Check Temporal Server connection
    temporal_host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    host_parts = temporal_host.split(":")
    t_host = host_parts[0]
    t_port = int(host_parts[1]) if len(host_parts) > 1 else 7233

    print(f"[*] Probing Temporal Server at {temporal_host}...")
    if check_port(t_host, t_port, timeout=2.0):
        print(f"    [OK] Temporal Server detected on {temporal_host}")
    else:
        print(f"    [WARN] Could not reach Temporal Server on {temporal_host}.")
        print("    Ensure your Temporal container is running (e.g., 'docker start aisoc-temporal' or 'docker compose up -d').")
        print("    Proceeding to launch processes anyway (they will auto-retry)...\n")

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

    print("\n[*] Spawning Worker Runner and FastAPI Gateway...")
    print(f"    - API Gateway URL:   http://localhost:{api_port}")
    print(f"    - API Docs URL:      http://localhost:{api_port}/docs")
    print("    - Temporal Web UI:   http://localhost:8233")
    print("=" * 60)
    print("Press Ctrl+C to stop all services.\n")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

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
            ],
            env=env,
        )
        processes.append(api_proc)

        # Wait for any process to terminate or keyboard interrupt
        while True:
            for p in processes:
                ret = p.poll()
                if ret is not None:
                    print(f"\n[!] Process {p.pid} exited with code {ret}")
                    return
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[*] Shutting down UAOS services gracefully...")
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
