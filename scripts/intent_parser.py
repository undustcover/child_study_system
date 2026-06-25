"""Controlled natural-language intent parsing for the stage 6 virtual device."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re
from typing import Any, Protocol


class ParseAction(StrEnum):
    COMMAND = "command"
    CLARIFY = "clarify"
    ABANDONED = "abandoned"
    UNRECOGNIZED = "unrecognized"
    NEGATED = "negated"


@dataclass(frozen=True)
class IntentCandidate:
    command: str
    phrase: str


@dataclass(frozen=True)
class ParseResult:
    action: ParseAction
    text: str
    command: str | None = None
    candidates: list[IntentCandidate] = field(default_factory=list)
    message_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class LLMIntentProvider(Protocol):
    """Future extension point for model-backed intent recognition."""

    def parse(self, text: str, context: dict[str, Any]) -> ParseResult | None:
        """Return a parse result or None when the provider declines."""


class DisabledLLMIntentProvider:
    def parse(self, text: str, context: dict[str, Any]) -> ParseResult | None:
        return None


@dataclass
class ClarificationState:
    candidates: list[IntentCandidate]
    attempts: int = 0


class ControlledIntentParser:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        llm_provider: LLMIntentProvider | None = None,
    ) -> None:
        parser_config = config.get("intent_parser", config)
        language_config = config.get("language", {})
        configured_phrases = language_config.get("command_phrases", {})
        self.commands: dict[str, list[str]] = {
            command: list(configured_phrases.get(command) or details.get("phrases", []))
            for command, details in parser_config.get("commands", {}).items()
        }
        self.negation_words: list[str] = list(parser_config.get("negation_words", []))
        self.max_clarification_attempts = int(parser_config.get("max_clarification_attempts", 2))
        self.llm_provider = llm_provider or DisabledLLMIntentProvider()
        self._clarification: ClarificationState | None = None

    @property
    def has_pending_clarification(self) -> bool:
        return self._clarification is not None

    def parse(self, text: str) -> ParseResult:
        normalized = _normalize(text)
        if not normalized:
            return ParseResult(ParseAction.UNRECOGNIZED, text, message_key="unrecognized")

        if self._clarification:
            return self._parse_clarification_answer(text, normalized)

        if self._is_negated(normalized):
            return ParseResult(ParseAction.NEGATED, text, message_key="negated")

        candidates = self._match_candidates(normalized)
        if len(candidates) == 1:
            candidate = candidates[0]
            return ParseResult(
                ParseAction.COMMAND,
                text,
                command=candidate.command,
                candidates=candidates,
                payload=_extract_payload(normalized),
            )
        if len(candidates) > 1:
            self._clarification = ClarificationState(candidates=candidates)
            return ParseResult(ParseAction.CLARIFY, text, candidates=candidates, message_key="clarify")

        provider_result = self.llm_provider.parse(text, {"commands": self.commands})
        if provider_result:
            return provider_result
        return ParseResult(ParseAction.UNRECOGNIZED, text, message_key="unrecognized")

    def reset_clarification(self) -> None:
        self._clarification = None

    def abandon_clarification(self, text: str = "") -> ParseResult:
        self._clarification = None
        return ParseResult(ParseAction.ABANDONED, text, message_key="clarify_abandoned")

    def _match_candidates(self, normalized: str) -> list[IntentCandidate]:
        matches: list[IntentCandidate] = []
        for command, phrases in self.commands.items():
            for phrase in phrases:
                normalized_phrase = _normalize(phrase)
                if normalized_phrase and normalized_phrase in normalized:
                    matches.append(IntentCandidate(command=command, phrase=phrase))
                    break
        if not any(candidate.command == "EXTEND_CURRENT_TASK" for candidate in matches):
            if re.search(r"再学[一二两三四五六七八九十\d]+分钟", normalized):
                matches.append(IntentCandidate(command="EXTEND_CURRENT_TASK", phrase="再学N分钟"))
        if not any(candidate.command == "EXTEND_BREAK" for candidate in matches):
            if re.search(r"再休息[一二两三四五六七八九十\d]+分钟", normalized):
                matches.append(IntentCandidate(command="EXTEND_BREAK", phrase="再休息N分钟"))
        return matches

    def _parse_clarification_answer(self, text: str, normalized: str) -> ParseResult:
        state = self._clarification
        if state is None:
            return ParseResult(ParseAction.UNRECOGNIZED, text, message_key="unrecognized")

        if self._is_negated(normalized):
            self._clarification = None
            return ParseResult(ParseAction.ABANDONED, text, message_key="clarify_abandoned")

        selected = self._select_candidate_from_answer(normalized, state.candidates)
        if selected:
            self._clarification = None
            return ParseResult(
                ParseAction.COMMAND,
                text,
                command=selected.command,
                candidates=[selected],
                payload=_extract_payload(normalized),
            )

        state.attempts += 1
        if state.attempts >= self.max_clarification_attempts:
            self._clarification = None
            return ParseResult(ParseAction.ABANDONED, text, message_key="clarify_abandoned")
        return ParseResult(ParseAction.CLARIFY, text, candidates=state.candidates, message_key="clarify_retry")

    def _select_candidate_from_answer(
        self,
        normalized: str,
        candidates: list[IntentCandidate],
    ) -> IntentCandidate | None:
        ordinal = _ordinal_answer(normalized)
        if ordinal is not None and 0 <= ordinal < len(candidates):
            return candidates[ordinal]

        for candidate in candidates:
            command_alias = _normalize(candidate.command)
            phrase = _normalize(candidate.phrase)
            if command_alias and command_alias in normalized:
                return candidate
            if phrase and phrase in normalized:
                return candidate

        direct_matches = [candidate for candidate in self._match_candidates(normalized) if candidate in candidates]
        if len(direct_matches) == 1:
            return direct_matches[0]
        return None

    def _is_negated(self, normalized: str) -> bool:
        if normalized in {"不知道", "不清楚", "我不知道", "我不清楚", "没听清", "没听懂"}:
            return False
        return any(_normalize(word) in normalized for word in self.negation_words)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip().lower())


def _ordinal_answer(normalized: str) -> int | None:
    ordinals = {
        "1": 0,
        "一": 0,
        "第一个": 0,
        "第1个": 0,
        "2": 1,
        "二": 1,
        "第二个": 1,
        "第2个": 1,
        "3": 2,
        "三": 2,
        "第三个": 2,
        "第3个": 2,
    }
    for token, index in ordinals.items():
        if token in normalized:
            return index
    return None


def _extract_payload(normalized: str) -> dict[str, Any]:
    minutes = _extract_minutes(normalized)
    return {"minutes": minutes} if minutes is not None else {}


def _extract_minutes(normalized: str) -> int | None:
    digit_match = re.search(r"(\d+)\s*分钟", normalized)
    if digit_match:
        return int(digit_match.group(1))

    chinese_digits = {
        "一": 1,
        "两": 2,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    for word, value in chinese_digits.items():
        if f"{word}分钟" in normalized:
            return value
    return None
