"""
Persistent state management for Site Web Monitor.

Tracks the SITE WEB count and seen entry IDs to prevent duplicate
notifications. Uses atomic writes to survive crashes.

State is stored as JSON and persisted to disk. The primary deduplication
key is stable entry IDs from the history table checkboxes.
"""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from app.config import STATE_FILE_PATH

logger = logging.getLogger(__name__)


@dataclass
class MonitorState:
    """Persistent monitoring state."""
    last_count: int = 0
    seen_entry_ids: Set[str] = field(default_factory=set)
    last_website: Optional[str] = None
    last_timestamp: Optional[str] = None
    updated_at: Optional[str] = None
    is_first_run: bool = True
    # Track auth failure notification dedup
    auth_failure_notified: bool = False

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "last_count": self.last_count,
            "seen_entry_ids": sorted(self.seen_entry_ids),
            "last_website": self.last_website,
            "last_timestamp": self.last_timestamp,
            "updated_at": self.updated_at,
            "is_first_run": self.is_first_run,
            "auth_failure_notified": self.auth_failure_notified,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MonitorState":
        """Deserialize from a dictionary."""
        return cls(
            last_count=data.get("last_count", 0),
            seen_entry_ids=set(data.get("seen_entry_ids", [])),
            last_website=data.get("last_website"),
            last_timestamp=data.get("last_timestamp"),
            updated_at=data.get("updated_at"),
            is_first_run=data.get("is_first_run", True),
            auth_failure_notified=data.get("auth_failure_notified", False),
        )


def load_state(path: Optional[Path] = None) -> MonitorState:
    """Load state from disk.

    Returns a fresh MonitorState (is_first_run=True) if no state file exists.
    """
    target = path or STATE_FILE_PATH

    if not target.is_file():
        logger.info("No state file found at %s — starting fresh", target)
        return MonitorState()

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        state = MonitorState.from_dict(data)
        logger.info(
            "Loaded state: count=%d, seen_ids=%d, first_run=%s",
            state.last_count,
            len(state.seen_entry_ids),
            state.is_first_run,
        )
        return state
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error(
            "Corrupted state file at %s: %s — starting fresh", target, exc
        )
        return MonitorState()


def save_state(state: MonitorState, path: Optional[Path] = None) -> None:
    """Save state to disk atomically.

    Uses write-to-temp + rename to prevent corruption on crash.
    """
    target = path or STATE_FILE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)

    # Update timestamp
    state.updated_at = datetime.now(timezone.utc).isoformat()

    data = json.dumps(state.to_dict(), indent=2, ensure_ascii=False)

    # Atomic write: write to temp file, then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=".state_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename (on Windows this requires removing target first
        # if it exists, but os.replace handles this)
        os.replace(tmp_path, target)
        logger.debug("State saved to %s", target)

    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_state_baseline(
    state: MonitorState,
    count: int,
    entry_ids: Set[str],
    latest_website: Optional[str] = None,
    latest_timestamp: Optional[str] = None,
) -> None:
    """Update the state with new baseline data.

    Used both for first-run initialization and after processing new entries.
    """
    state.last_count = count
    state.seen_entry_ids.update(entry_ids)
    if latest_website:
        state.last_website = latest_website
    if latest_timestamp:
        state.last_timestamp = latest_timestamp
    state.is_first_run = False
    state.auth_failure_notified = False  # Reset on successful check
