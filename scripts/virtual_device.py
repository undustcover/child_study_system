"""Virtual ESP32-S3-BOX-3 device for stage 6 local testing."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import urlopen

import websockets

from intent_parser import ControlledIntentParser, ParseAction, ParseResult


DEFAULT_CONFIG_PATH = Path(__file__).with_name("virtual_device_config.json")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_backend_language_settings(config: dict[str, Any], ws_url: str) -> dict[str, Any] | None:
    language_config = config.get("language", {})
    if language_config.get("sync_from_backend") is False:
        return None
    settings_url = language_config.get("settings_url") or _language_settings_url_from_ws(ws_url)
    try:
        with urlopen(settings_url, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        print(f"无法同步后端语言配置，继续使用本地配置：{exc}", file=sys.stderr)
        return None


def apply_backend_language_settings(config: dict[str, Any], settings: dict[str, Any] | None) -> None:
    if not settings:
        return
    language = config.setdefault("language", {})
    for key in ("virtual_reply_templates", "command_phrases", "command_labels"):
        value = settings.get(key)
        if isinstance(value, dict):
            language[key] = value


def apply_device_config_sync(config: dict[str, Any], payload: dict[str, Any]) -> None:
    language_settings = payload.get("language_settings", {})
    if isinstance(language_settings, dict):
        apply_backend_language_settings(config, language_settings)
    device_settings = payload.get("device_settings", {})
    if isinstance(device_settings, dict):
        config["backend_device_settings"] = device_settings


def _language_settings_url_from_ws(ws_url: str) -> str:
    parsed = urlparse(ws_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    return urlunparse((scheme, parsed.netloc, "/api/language-settings", "", "", ""))


class SafeTemplateValues(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_template(config: dict[str, Any], key: str, **values: Any) -> str:
    template = (
        config.get("language", {})
        .get("virtual_reply_templates", config.get("reply_templates", {}))
        .get(key, key)
    )
    today = datetime.now().date().isoformat()
    template_values = SafeTemplateValues(
        {
            "student": "",
            "学生": "",
            "date": today,
            "日期": today,
            "task": "",
            "任务": "",
            "minutes": "",
            "分钟数": "",
        }
    )
    template_values.update(values)
    return template.format_map(template_values)


def command_label(config: dict[str, Any], command: str | None) -> str:
    if not command:
        return ""
    return (
        config.get("language", {})
        .get("command_labels", {})
        .get(command)
        or config.get("intent_parser", {}).get("commands", {}).get(command, {}).get("label", command)
    )


def build_device_url(config: dict[str, Any], device_id: str, override_url: str | None) -> str:
    if override_url:
        return override_url.format(device_id=device_id)
    template = config.get("connection", {}).get("url_template", "ws://localhost:8000/ws/device/{device_id}")
    return template.format(device_id=device_id)


def build_hello(config: dict[str, Any], device_id: str) -> dict[str, str]:
    device = config.get("device", {})
    return {
        "type": "device_hello",
        "device_id": device_id,
        "device_type": device.get("device_type", "virtual_box_3"),
        "firmware_version": device.get("firmware_version", "virtual-0.1.0"),
    }


def build_voice_command(device_id: str, text: str, result: ParseResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "voice_command",
        "device_id": device_id,
        "command": result.command,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(result.payload)
    return payload


def build_startup_query_command(device_id: str) -> dict[str, Any]:
    return build_voice_command(
        device_id,
        "启动后自动查询今日计划",
        ParseResult(ParseAction.COMMAND, "启动后自动查询今日计划", command="QUERY_TODAY_PLAN"),
    )


def is_disconnect_phrase(config: dict[str, Any], text: str) -> bool:
    phrases = config.get("control_phrases", {}).get("disconnect", ["断开连接"])
    return text in set(phrases)


def extract_template_values(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    task = payload.get("task") if isinstance(payload, dict) else None
    if not isinstance(task, dict):
        task = {}
    minutes = task.get("planned_minutes") or payload.get("minutes", "")
    task_name = task.get("title") or payload.get("task_name", "")
    return {
        "student": payload.get("student_name", ""),
        "学生": payload.get("student_name", ""),
        "date": payload.get("target_date") or datetime.now().date().isoformat(),
        "日期": payload.get("target_date") or datetime.now().date().isoformat(),
        "task": task_name,
        "任务": task_name,
        "minutes": minutes,
        "分钟数": minutes,
    }


def tts_enabled(config: dict[str, Any], cli_enabled: bool) -> bool:
    return cli_enabled or bool(config.get("tts", {}).get("enabled", False))


def speak_with_tts(text: str) -> None:
    if not text:
        return
    if platform.system() != "Windows":
        print("当前系统未启用电脑TTS：仅支持Windows本地语音。")
        return
    escaped = text.replace("'", "''")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$speaker.Speak('{escaped}')"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", command], check=False, timeout=30)


async def maybe_speak_with_tts(text: str, enabled: bool) -> None:
    if not enabled:
        return
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, speak_with_tts, text)


async def receive_messages(websocket: websockets.ClientConnection, config: dict[str, Any], *, use_tts: bool) -> None:
    async for raw_message in websocket:
        message = json.loads(raw_message)
        message_type = message.get("type")
        template_values = extract_template_values(message)

        if message_type == "speak":
            text = message.get("text", "")
            message_id = message.get("message_id", "")
            print(f"[{render_template(config, 'speak_prefix', **template_values)}] {text}")
            await maybe_speak_with_tts(text, use_tts)
            await websocket.send(json.dumps({"type": "playback_finished", "message_id": message_id}, ensure_ascii=False))
            print(render_template(config, "playback_finished", message_id=message_id, **template_values))
            continue

        if message_type == "display_state":
            state = message.get("state", "")
            backend_message = message.get("payload", {}).get("message", "")
            print(f"[{render_template(config, 'display_state_prefix', **template_values)}] {state} {backend_message}".rstrip())
            continue

        if message_type == "sync_state":
            state = message.get("state", "")
            payload = message.get("payload", {})
            if state == "device_config" and isinstance(payload, dict):
                apply_device_config_sync(config, payload)
                version = payload.get("config_version", "")
                print(f"[{render_template(config, 'sync_state_prefix', **template_values)}] {state} {version}".rstrip())
                continue
            print(f"[{render_template(config, 'sync_state_prefix', **template_values)}] {state}")
            continue

        print(f"[unknown] {message}")


async def read_user_line(prompt: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def send_user_commands(
    websocket: websockets.ClientConnection,
    config: dict[str, Any],
    parser: ControlledIntentParser,
    device_id: str,
) -> None:
    prompt = render_template(config, "prompt")
    clarification_timeout = int(config.get("intent_parser", {}).get("clarification_timeout_seconds", 30))
    while True:
        try:
            if parser.has_pending_clarification:
                text = (await asyncio.wait_for(read_user_line(prompt), timeout=clarification_timeout)).strip()
            else:
                text = (await read_user_line(prompt)).strip()
        except asyncio.TimeoutError:
            result = parser.abandon_clarification()
            print(render_parser_feedback(config, result))
            continue
        except EOFError:
            return

        if text in {"/quit", "/exit"}:
            await websocket.close()
            return
        if is_disconnect_phrase(config, text):
            print(render_template(config, "disconnect_requested"))
            await websocket.close()
            return
        if not text:
            continue

        result = parser.parse(text)
        if result.action == ParseAction.COMMAND and result.command:
            await websocket.send(json.dumps(build_voice_command(device_id, text, result), ensure_ascii=False))
            print(render_template(config, "command_sent", command=command_label(config, result.command)))
            continue

        print(render_parser_feedback(config, result))


def render_parser_feedback(config: dict[str, Any], result: ParseResult) -> str:
    key = result.message_key or result.action.value
    if result.candidates:
        options = " / ".join(
            f"{index + 1}.{command_label(config, candidate.command)}"
            for index, candidate in enumerate(result.candidates)
        )
        return render_template(config, key, options=options)
    return render_template(config, key)


async def run_virtual_device(config: dict[str, Any], *, device_id: str, url: str) -> None:
    parser = ControlledIntentParser(config)
    use_tts = tts_enabled(config, False)
    async with websockets.connect(url) as websocket:
        print(render_template(config, "connection_opened", url=url))
        await websocket.send(json.dumps(build_hello(config, device_id), ensure_ascii=False))
        await websocket.send(json.dumps(build_startup_query_command(device_id), ensure_ascii=False))
        print(render_template(config, "startup_query_sent"))
        receiver = asyncio.create_task(receive_messages(websocket, config, use_tts=use_tts))
        sender = asyncio.create_task(send_user_commands(websocket, config, parser, device_id))
        done, pending = await asyncio.wait({receiver, sender}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except websockets.ConnectionClosed:
                pass
        print(render_template(config, "connection_closed"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a virtual BOX-3 device against the backend WebSocket.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to virtual_device_config.json.")
    parser.add_argument("--device-id", help="Override the configured virtual device id.")
    parser.add_argument("--url", help="Override backend WebSocket URL. Supports {device_id}.")
    parser.add_argument("--tts", action="store_true", help="Enable optional computer TTS for backend speak messages.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    device_id = args.device_id or config.get("device", {}).get("device_id", "virtual-box3-001")
    url = build_device_url(config, device_id, args.url)
    apply_backend_language_settings(config, load_backend_language_settings(config, url))
    if args.tts:
        config.setdefault("tts", {})["enabled"] = True
    try:
        asyncio.run(run_virtual_device(config, device_id=device_id, url=url))
    except KeyboardInterrupt:
        print()
        print(render_template(config, "connection_closed"))
    except OSError as exc:
        print(f"无法连接后端 WebSocket：{exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
