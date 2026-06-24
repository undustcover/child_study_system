import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from intent_parser import ControlledIntentParser, ParseAction  # noqa: E402
from virtual_device import build_hello, build_voice_command, render_parser_feedback  # noqa: E402


def load_virtual_config() -> dict:
    with (PROJECT_ROOT / "scripts" / "virtual_device_config.json").open("r", encoding="utf-8") as file:
        return json.load(file)


def test_controlled_phrase_becomes_device_voice_command() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    result = parser.parse("我开始学习了")
    payload = build_voice_command("virtual-box3-001", "我开始学习了", result)

    assert result.action == ParseAction.COMMAND
    assert payload["type"] == "voice_command"
    assert payload["device_id"] == "virtual-box3-001"
    assert payload["command"] == "START_STUDY"
    assert payload["text"] == "我开始学习了"


def test_multiple_intents_enter_clarification_then_choose_one() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    first = parser.parse("开始学习然后完成了")
    second = parser.parse("第一个")

    assert first.action == ParseAction.CLARIFY
    assert [candidate.command for candidate in first.candidates] == ["START_STUDY", "COMPLETE_STUDY"]
    assert second.action == ParseAction.COMMAND
    assert second.command == "START_STUDY"
    assert parser.has_pending_clarification is False


def test_clarification_feedback_uses_chinese_command_labels() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    result = parser.parse("开始学习然后完成了")
    feedback = render_parser_feedback(config, result)

    assert "开始学习" in feedback
    assert "完成学习" in feedback
    assert "START_STUDY" not in feedback
    assert "COMPLETE_STUDY" not in feedback


def test_negated_sentence_is_not_sent_as_command() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    result = parser.parse("不要开始学习")

    assert result.action == ParseAction.NEGATED
    assert result.command is None


def test_clarification_abandons_after_configured_retries() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    parser.parse("开始学习然后完成了")
    retry = parser.parse("我不知道")
    abandoned = parser.parse("还是不清楚")

    assert retry.action == ParseAction.CLARIFY
    assert abandoned.action == ParseAction.ABANDONED
    assert parser.has_pending_clarification is False


def test_extension_minutes_are_kept_in_protocol_payload() -> None:
    config = load_virtual_config()
    parser = ControlledIntentParser(config)

    result = parser.parse("再学5分钟")
    payload = build_voice_command("virtual-box3-001", "再学5分钟", result)

    assert result.command == "EXTEND_CURRENT_TASK"
    assert payload["minutes"] == 5


def test_virtual_device_hello_uses_configured_box3_identity() -> None:
    config = load_virtual_config()

    hello = build_hello(config, "virtual-box3-001")

    assert hello == {
        "type": "device_hello",
        "device_id": "virtual-box3-001",
        "device_type": "virtual_box_3",
        "firmware_version": "virtual-0.1.0",
    }
