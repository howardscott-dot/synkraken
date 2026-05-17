from __future__ import annotations

import json
import re
from typing import Any


FINAL_LINE_RE = re.compile(r'^[A-Z0-9_-]+(?:\s|:).+$')
NOISY_PREFIXES = (
    '{"content":',
    '{"message":',
    '{"messages":',
    '{"type":',
)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('```') and stripped.endswith('```'):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return '\n'.join(lines[1:-1]).strip()
    return stripped


def _candidate_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def normalize_text_output(raw: str) -> str:
    text = _strip_fences(raw)
    if not text:
        return text

    # Prefer the last strong-looking answer line when tools/chat logs precede it.
    lines = _candidate_lines(text)
    for line in reversed(lines):
        if FINAL_LINE_RE.match(line):
            return line

    # Remove obvious tool/status chatter lines and keep remaining content.
    filtered: list[str] = []
    for line in lines:
        lower = line.lower()
        if lower.startswith('tool ') or lower.startswith('using tool'):
            continue
        if 'todo_write' in lower or 'tool call' in lower or 'tool result' in lower:
            continue
        if lower.startswith('thinking:') or lower.startswith('reasoning:'):
            continue
        filtered.append(line)
    if filtered:
        return '\n'.join(filtered).strip()

    return text.strip()


def normalize_structured_output(parsed: Any) -> str | None:
    if parsed is None:
        return None
    if isinstance(parsed, str):
        stripped = parsed.strip()
        return normalize_text_output(stripped) if stripped else None
    if isinstance(parsed, list):
        parts: list[str] = []
        for item in parsed:
            extracted = normalize_structured_output(item)
            if extracted:
                parts.append(extracted)
        if not parts:
            return None
        joined = '\n'.join(parts).strip()
        return normalize_text_output(joined) if joined else None
    if isinstance(parsed, dict):
        # Common chat / API keys.
        for key in ('reply', 'message', 'text', 'content', 'output', 'final_response', 'response'):
            if key in parsed:
                extracted = normalize_structured_output(parsed.get(key))
                if extracted:
                    return extracted

        # OpenAI-style choices/messages.
        if 'choices' in parsed:
            extracted = normalize_structured_output(parsed.get('choices'))
            if extracted:
                return extracted
        if 'messages' in parsed:
            extracted = normalize_structured_output(parsed.get('messages'))
            if extracted:
                return extracted
        if 'payloads' in parsed:
            extracted = normalize_structured_output(parsed.get('payloads'))
            if extracted:
                return extracted
        if 'result' in parsed:
            extracted = normalize_structured_output(parsed.get('result'))
            if extracted:
                return extracted
        if 'assistant' in parsed:
            extracted = normalize_structured_output(parsed.get('assistant'))
            if extracted:
                return extracted

        # Some wrappers return dicts with content arrays.
        for key in ('items', 'parts', 'data'):
            if key in parsed:
                extracted = normalize_structured_output(parsed.get(key))
                if extracted:
                    return extracted
        return None
    return str(parsed).strip() or None


def try_parse_json_text(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped or not stripped.startswith(('{', '[')):
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None
