"""Append-only audit trail at output/audit_trail.json.

The file is a JSON array of AuditEvent objects. Every write reads the existing
array, appends, and atomically replaces the file, so earlier runs are never
removed. If the file cannot be parsed it is renamed (kept), never overwritten.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import AUDIT_PATH
from .models import AuditEvent, AuditEventType

_LOCK = threading.Lock()
MAX_FIELD_CHARS = 8_000


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _clip(value: Any) -> Any:
    """Keep audit entries readable: long strings are cut, with the original length noted."""
    if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
        return value[:MAX_FIELD_CHARS] + f"... [truncated, {len(value)} chars]"
    if isinstance(value, dict):
        return {k: _clip(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clip(v) for v in value]
    return value


class AuditLog:
    def __init__(self, run_id: str, path: Path = AUDIT_PATH):
        self.run_id = run_id
        self.path = path
        self.seq = 0
        self.shop_date: str | None = None
        self.ticket_id: int | None = None

    def _read_existing(self) -> list:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        # Never wipe: keep the unreadable file under a new name and start a fresh array.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        self.path.rename(self.path.with_name(f"audit_trail.unreadable-{stamp}.json"))
        return []

    def log(self, event: AuditEventType, *, agent: str | None = None, depth: int | None = None,
            chain: list[str] | None = None, step: int | None = None, model: str | None = None,
            **detail: Any) -> AuditEvent:
        with _LOCK:
            self.seq += 1
            entry = AuditEvent(
                run_id=self.run_id, seq=self.seq, ts_utc=now_utc(), shop_date=self.shop_date,
                event=event, ticket_id=self.ticket_id, agent=agent, depth=depth,
                chain=chain or [], step=step, model=model, detail=_clip(detail),
            )
            events = self._read_existing()
            events.append(entry.model_dump(mode="json"))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8")
            _replace(tmp, self.path)
            return entry


def _replace(src: Path, dest: Path, attempts: int = 20) -> None:
    """os.replace with retries: on Windows the swap fails while a reader (e.g. GET /events) has the file open."""
    for i in range(attempts):
        try:
            os.replace(src, dest)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05)


def read_events(path: Path = AUDIT_PATH) -> list:
    """Read the audit trail for the API. Retries briefly if a write is in progress."""
    for _ in range(20):
        try:
            if not path.exists():
                return []
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.05)
    return []
