# Fleet Studio

Desired-state governance and assurance control plane for Hermes agent fleets.

## Architecture

- **Frontend**: Next.js 16 (React 19, Tailwind CSS, Lucide icons, Recharts, @xyflow/react) — runs on port 3000
- **Backend**: FastAPI (Python 3.12+) — runs on port 8001
- **Database**: PostgreSQL (via SQLAlchemy + asyncpg + Alembic)
- **Agent Runtime**: Hermes WebSocket JSON-RPC gateway & daemon hooks

## Directory Structure

- `frontend/`: The Next.js web application UI
- `backend/`: FastAPI backend with governance, assurance, and database models
- `agents/`: Fleet control plugins, daemons, and profile materializer for Hermes
- `deploy/`: Docker Compose and Helm deployment manifests

## Quick Start

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -e ".[dev]"
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at `http://localhost:3000` and automatically proxies requests:
- `/api/v1/*`, `/auth/*`, `/health` -> Fleet Studio Backend (`http://127.0.0.1:8001`)
- `/api/fleet/*`, `/api/skills/*`, `/api/hermes/*`, `/api/schedules*`, `/stream/*` -> Autonomous Agent Orchestrator (`http://127.0.0.1:8000`)

### 3. All-in-One Launcher (Windows)

Double click or run:
```cmd
start.bat
```

### 4. Full Stack with Docker

```bash
cd deploy
docker compose up -d
```
