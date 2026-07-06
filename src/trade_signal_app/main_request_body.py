from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import parse_qs

from .main_settings import _get_first


def _read_body(handler: BaseHTTPRequestHandler) -> str:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return ""
    return handler.rfile.read(length).decode("utf-8")


def _strategy_description_from_body(handler: BaseHTTPRequestHandler) -> tuple[str, dict[str, list[str]]]:
    raw = _read_body(handler)
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("JSON 请求体无效。") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON 请求体根节点必须是对象。")
        description = str(payload.get("description") or payload.get("strategy_description") or "")
        lang = str(payload.get("lang") or "")
        form = {"strategy_description": [description]}
        if lang:
            form["lang"] = [lang]
        return description.strip(), form
    form = parse_qs(raw)
    description = _get_first(form, "strategy_description", _get_first(form, "description", ""))
    return description.strip(), form


__all__ = [
    "_read_body",
    "_strategy_description_from_body",
]
