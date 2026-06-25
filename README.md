# Children Learning Planner P1-A

Version: `V0.0.3`

P1-A is the first computer-side prototype for a student learning plan, reminder,
timing, rest, voice execution, and statistics loop.

Current product direction:

- Parents use the computer web console.
- The student does not use the computer UI.
- The student will execute tasks through ESP32-S3-BOX-3 voice interaction.
- Before real hardware integration, a virtual BOX-3 device will simulate the same protocol.

## Current Stage

P1-A first backend development round is complete and accepted. The project is
ready to wait for the real ESP32-S3-BOX-3 device before entering firmware
development and backend-device integration.

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
- Parent console device, statistics, and correction pages
- Parent console device settings page and language customization page
- Today-plan broadcast over the device protocol
- Device/language config sync over `sync_state: device_config`
- Final-task completion broadcast
- Stage 8 automated end-to-end acceptance test
- Manual user acceptance checklist
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
`scripts/virtual_device_config.json`. When the backend is available, language
settings are synchronized from `/api/language-settings`, and connected devices
receive configuration updates through WebSocket `sync_state` messages.

Useful configuration endpoints:

```text
GET  /api/devices/settings/default
PUT  /api/devices/settings/default
GET  /api/devices/{device_id}/settings
PUT  /api/devices/{device_id}/settings
POST /api/devices/{device_id}/sync-config
GET  /api/language-settings
PUT  /api/language-settings
POST /api/language-settings/reset
```

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

## Release Notes

### V0.0.3

- 第一次后端开发完成。
- 阶段8第二轮用户验收完成。
- 阶段8-A设备设置、语言自定义、今日计划播报和配置同步基础能力完成。
- 下一步等待真实ESP32-S3-BOX-3到货后进入设备固件开发和后端联调。

## Project Notes

Read these documents before continuing work in a new conversation:

1. `开发/P1-A详细开发进度表.md`
2. `开发/P1-A阶段8用户验收清单.md`
3. `开发/项目开发计划.md`
4. `开发/P1-A电脑端技术规格.md`
5. `实施方案/后端开发粗讨论.md`
6. `实施方案/todolist-MVP实施方案.md`
7. `构思/Todolist-MVP.md`
