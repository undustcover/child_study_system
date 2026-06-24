from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.api.health import router as health_router
from app.core.config import settings
from app.api.calendar_plans import router as calendar_plans_router
from app.api.commands import router as commands_router
from app.api.daily_tasks import router as daily_tasks_router
from app.api.holidays import router as holidays_router
from app.core.database import init_db

templates = Jinja2Templates(directory=str(Path(__file__).parent / "web" / "templates"))


def create_app() -> FastAPI:
    init_db()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="P1-A computer backend for calendar plans, reminders, sessions, and BOX-3 device protocol.",
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(calendar_plans_router, prefix="/api")
    app.include_router(commands_router, prefix="/api")
    app.include_router(daily_tasks_router, prefix="/api")
    app.include_router(holidays_router, prefix="/api")

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "app_name": settings.app_name,
                "app_version": settings.app_version,
            },
        )

    @app.websocket("/ws/device/{device_id}")
    async def device_ws(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "sync_state",
                "device_id": device_id,
                "message": "Device WebSocket skeleton connected.",
            }
        )
        await websocket.receive_text()

    return app


app = create_app()
