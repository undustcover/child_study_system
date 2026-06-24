# Children Learning Planner P1-A

Version: `0.01`

P1-A is the first computer-side prototype for a student learning plan, reminder,
timing, rest, voice execution, and statistics loop.

Current product direction:

- Parents use the computer web console.
- The student does not use the computer UI.
- The student will execute tasks through ESP32-S3-BOX-3 voice interaction.
- Before real hardware integration, a virtual BOX-3 device will simulate the same protocol.

## Current Stage

The project is in stage 1: computer-side project skeleton.

Implemented skeleton:

- FastAPI backend
- Health check API
- Parent web console landing page
- Device WebSocket placeholder
- Docker and Docker Compose local deployment files
- Persistent `data/` directory for SQLite

## Local Run

Install dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Start the backend:

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/api/health
```

## Docker Run

```powershell
docker compose up --build
```

The backend will be available at:

```text
http://localhost:8000
```

SQLite data is stored under:

```text
data/
```

## Windows Python Note

This workspace uses a project-local `.venv` for local development. Prefer the
commands above instead of the global `python` command, because the host machine
may have multiple Python installations.

## Project Notes

Read these documents before continuing work in a new conversation:

1. `开发/项目开发计划.md`
2. `开发/P1-A电脑端技术规格.md`
3. `实施方案/后端开发粗讨论.md`
4. `实施方案/todolist-MVP实施方案.md`
5. `构思/Todolist-MVP.md`
