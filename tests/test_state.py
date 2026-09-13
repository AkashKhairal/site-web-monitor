"""Tests for app.state module."""
import json
import os
import tempfile
from pathlib import Path

import pytest

from app.state import MonitorState, load_state, save_state, update_state_baseline


@pytest.fixture
def tmp_state_path(tmp_path):
    """Provide a temporary state file path."""
    return tmp_path / "state.json"


class TestMonitorState:
    """Test MonitorState dataclass."""

    def test_default_state(self):
        state = MonitorState()
        assert state.last_count == 0
        assert state.seen_entry_ids == set()
        assert state.is_first_run is True
        assert state.auth_failure_notified is False

    def test_round_trip_serialization(self):
        state = MonitorState(
            last_count=5,
            seen_entry_ids={"123", "456", "789"},
            last_website="example.com",
            last_timestamp="2026/08/24 18:00:00",
            is_first_run=False,
        )
        data = state.to_dict()
        restored = MonitorState.from_dict(data)
        assert restored.last_count == 5
        assert restored.seen_entry_ids == {"123", "456", "789"}
        assert restored.last_website == "example.com"
        assert restored.is_first_run is False

    def test_from_dict_with_missing_keys(self):
        """Gracefully handle missing keys (forward compatibility)."""
        data = {"last_count": 3}
        state = MonitorState.from_dict(data)
        assert state.last_count == 3
        assert state.seen_entry_ids == set()
        assert state.is_first_run is True

    def test_seen_entry_ids_sorted_in_json(self):
        """Entry IDs should be sorted in serialized form for determinism."""
        state = MonitorState(seen_entry_ids={"c", "a", "b"})
        data = state.to_dict()
        assert data["seen_entry_ids"] == ["a", "b", "c"]


class TestLoadState:
    """Test state loading from disk."""

    def test_no_file_returns_fresh_state(self, tmp_state_path):
        state = load_state(tmp_state_path)
        assert state.is_first_run is True
        assert state.last_count == 0

    def test_loads_valid_state(self, tmp_state_path):
        data = {
            "last_count": 7,
            "seen_entry_ids": ["100", "200"],
            "is_first_run": False,
        }
        tmp_state_path.write_text(json.dumps(data), encoding="utf-8")
        state = load_state(tmp_state_path)
        assert state.last_count == 7
        assert state.seen_entry_ids == {"100", "200"}
        assert state.is_first_run is False

    def test_corrupted_json_returns_fresh(self, tmp_state_path):
        tmp_state_path.write_text("not valid json {{{", encoding="utf-8")
        state = load_state(tmp_state_path)
        assert state.is_first_run is True


class TestSaveState:
    """Test state saving to disk."""

    def test_saves_and_loads(self, tmp_state_path):
        state = MonitorState(
            last_count=10,
            seen_entry_ids={"a1", "b2"},
            is_first_run=False,
        )
        save_state(state, tmp_state_path)

        assert tmp_state_path.is_file()
        loaded = load_state(tmp_state_path)
        assert loaded.last_count == 10
        assert loaded.seen_entry_ids == {"a1", "b2"}

    def test_atomic_no_temp_file_left(self, tmp_state_path):
        """After save, no .tmp files should remain."""
        state = MonitorState(last_count=1)
        save_state(state, tmp_state_path)

        parent = tmp_state_path.parent
        tmp_files = list(parent.glob(".state_*.tmp"))
        assert len(tmp_files) == 0

    def test_overwrite_existing(self, tmp_state_path):
        state1 = MonitorState(last_count=1)
        save_state(state1, tmp_state_path)

        state2 = MonitorState(last_count=2)
        save_state(state2, tmp_state_path)

        loaded = load_state(tmp_state_path)
        assert loaded.last_count == 2

    def test_updated_at_is_set(self, tmp_state_path):
        state = MonitorState()
        assert state.updated_at is None
        save_state(state, tmp_state_path)
        assert state.updated_at is not None


class TestUpdateStateBaseline:
    """Test baseline update logic."""

    def test_first_run_baseline(self):
        state = MonitorState()
        assert state.is_first_run is True

        update_state_baseline(
            state,
            count=7,
            entry_ids={"100", "200", "300"},
            latest_website="example.com",
            latest_timestamp="2026/08/24 18:00:00",
        )

        assert state.last_count == 7
        assert state.seen_entry_ids == {"100", "200", "300"}
        assert state.last_website == "example.com"
        assert state.is_first_run is False

    def test_incremental_update(self):
        state = MonitorState(
            last_count=3,
            seen_entry_ids={"100", "200", "300"},
            is_first_run=False,
        )

        update_state_baseline(
            state,
            count=5,
            entry_ids={"400", "500"},
            latest_website="new-site.com",
        )

        # Should merge, not replace
        assert state.last_count == 5
        assert state.seen_entry_ids == {"100", "200", "300", "400", "500"}
        assert state.last_website == "new-site.com"

    def test_resets_auth_failure_flag(self):
        state = MonitorState(auth_failure_notified=True)
        update_state_baseline(state, count=1, entry_ids={"1"})
        assert state.auth_failure_notified is False
