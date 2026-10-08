"""Restore data/campus_customs_new.db from the original before a full ticket run.

The original data/campus_customs.db is only read. Payment requests and drafts
and incoming-stock records belong to the database state they were made against, so they are archived
(never deleted) and a fresh, empty list is started. The audit trail is untouched.

Usage:  python -m backend.reset_db
"""

import shutil
from datetime import datetime, timezone

from .config import DRAFTS_PATH, INCOMING_PATH, ORIGINAL_DB, REQUESTS_PATH, WORKING_DB


def reset_working_db() -> dict:
    if WORKING_DB.resolve() == ORIGINAL_DB.resolve():
        raise RuntimeError("Refusing to reset: the working DB path points at the original.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archived = []
    for path in (REQUESTS_PATH, DRAFTS_PATH, INCOMING_PATH):
        if path.exists() and path.read_text(encoding="utf-8").strip() not in ("", "[]"):
            dest = path.parent / "archive" / f"{path.stem}-{stamp}.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(path, dest)
            archived.append(str(dest))
        path.write_text("[]", encoding="utf-8")
    return {"copied_from": str(ORIGINAL_DB), "copied_to": str(WORKING_DB), "archived": archived, "at_utc": stamp}


if __name__ == "__main__":
    print(reset_working_db())
