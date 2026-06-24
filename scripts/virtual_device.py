"""Virtual ESP32-S3-BOX-3 device for stage 6 local testing."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

import websockets

from intent_parser import ControlledIntentParser, ParseAction, ParseResult


DEFAULT_CONFIG_PATH = Path(__file__).with_name("virtual_device_config.json")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def render_template(config: dict[str, Any], key: str, **values: Any) -> str:
    template = config.get("reply_templates", {}).get(key, key)
    return template.format(**values)


def command_label(config: dict[str, Any], command: str | None) -> str:
    if not command:
        return ""
    return config.get("intent_parser", {}).get("commands", {}).get(command, {}).get("label", command)


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


async def receive_messages(websocket: websockets.ClientConnection, config: dict[str, Any]) -> None:
    async for raw_message in websocket:
        message = json.loads(raw_message)
        message_type = message.get("type")

        if message_type == "speak":
            text = message.get("text", "")
            message_id = message.get("message_id", "")
            print(f"[{render_template(config, 'speak_prefix')}] {text}")
            await websocket.send(json.dumps({"type": "playback_finished", "message_id": message_id}, ensure_ascii=False))
            print(render_template(config, "playback_finished", message_id=message_id))
            continue

        if message_type == "display_state":
            state = message.get("state", "")
            backend_message = message.get("payload", {}).get("message", "")
            print(f"[{render_template(config, 'display_state_prefix')}] {state} {backend_message}".rstrip())
            continue

        if message_type == "sync_state":
            state = message.get("state", "")
            print(f"[{render_template(config, 'sync_state_prefix')}] {state}")
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
    while True:
        try:
            text = (await read_user_line(prompt)).strip()
        except EOFError:
            return

        if text in {"/quit", "/exit"}:
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
    async with websockets.connect(url) as websocket:
        print(render_template(config, "connection_opened", url=url))
        await websocket.send(json.dumps(build_hello(config, device_id), ensure_ascii=False))
        receiver = asyncio.create_task(receive_messages(websocket, config))
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    device_id = args.device_id or config.get("device", {}).get("device_id", "virtual-box3-001")
    url = build_device_url(config, device_id, args.url)
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
