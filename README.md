# Children Learning Planner P1-A

Version: `V 0.0.2`

P1-A is the first computer-side prototype for a student learning plan, reminder,
timing, rest, voice execution, and statistics loop.

Current product direction:

- Parents use the computer web console.
- The student does not use the computer UI.
- The student will execute tasks through ESP32-S3-BOX-3 voice interaction.
- Before real hardware integration, a virtual BOX-3 device will simulate the same protocol.

## Current Stage

The project is in stage 7: parent web management console.

Implemented so far:

- FastAPI backend
- Health check API
- Parent web console landing page
- Device WebSocket protocol
- Virtual BOX-3 CLI simulator
- Controlled Chinese natural-language intent parser
- Parent console visual direction selected as option B: warm family style
- Parent console static homepage shell
- Parent console homepage reads `/api/dashboard/today`
- Parent console calendar plan create/edit page
- Parent console single-day exceptions, vacation ranges, and holiday sync entries
- Docker and Docker Compose local deployment files
- Persistent `data/` directory for SQLite

## Local Run

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/api/health
```

## Virtual BOX-3 Device

Start the backend first, then run:

```powershell
.\.venv\Scripts\python.exe scripts\virtual_device.py
```

The virtual device connects to `ws://localhost:8000/ws/device/virtual-box3-001`,
sends `device_hello`, prints backend `speak` messages, and sends
`playback_finished` after each printed broadcast. Student utterances are typed in
Chinese and converted into the same `voice_command` protocol used by the real
device. Phrase tables and reply templates live in
`scripts/virtual_device_config.json`.

Manual smoke phrases:

```text
今天计划
开始学习
暂停
继续
完成了
开始学习然后完成了
第一个
不要开始学习
粘贴
/quit
```

In development mode, the default SQLite database uses the current model
structure. If `data/app.db` is stale, the app rebuilds it instead of preserving
old prototype data.

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

1. `开发/P1-A详细开发进度表.md`
2. `开发/项目开发计划.md`
3. `开发/P1-A电脑端技术规格.md`
4. `实施方案/后端开发粗讨论.md`
5. `实施方案/todolist-MVP实施方案.md`
6. `构思/Todolist-MVP.md`
