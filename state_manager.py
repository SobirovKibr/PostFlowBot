"""
State management module for Telegram Userbot.
Persists runtime configuration (interval, window, sticker toggle, indices) to state.json
so settings survive restarts and can be modified dynamically via Saved Messages commands.
"""

import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import pytz

import config
from logger import logger

STATE_FILE = Path(__file__).resolve().parent / "state.json"


class BotState:
    """Manages persistent bot state synchronized with state.json."""

    def __init__(self):
        self.state_file = STATE_FILE
        self._data: Dict[str, Any] = self._load_initial_state()

    def _load_initial_state(self) -> Dict[str, Any]:
        """Loads state from state.json if present; otherwise creates default from config."""
        default_state = {
            "is_scheduler_running": True,
            "interval_minutes": config.INTERVAL_MINUTES,
            "start_time": config.START_TIME_STR,
            "end_time": config.END_TIME_STR,
            "timezone": config.TIMEZONE_STR,
            "message_index": 0,
            "sticker_enabled": False,
            "current_sticker_set": None,
            "sticker_index": 0,
            "min_delay_between_groups": config.MIN_DELAY_BETWEEN_GROUPS,
            "max_delay_between_groups": config.MAX_DELAY_BETWEEN_GROUPS,
            "round_jitter_seconds": config.ROUND_JITTER_SECONDS,
            "last_run_timestamp": None,
            "next_run_timestamp": None,
        }

        if not self.state_file.exists():
            self._save(default_state)
            return default_state

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Ensure all default keys exist
            for key, val in default_state.items():
                if key not in loaded:
                    loaded[key] = val
            return loaded
        except Exception as e:
            logger.error(f"Error loading {self.state_file}: {e}. Resetting to defaults.")
            self._save(default_state)
            return default_state

    def _save(self, data: Optional[Dict[str, Any]] = None):
        """Writes state dictionary to state.json atomically."""
        if data is None:
            data = self._data
        try:
            tmp_file = self.state_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"Failed to write state file {self.state_file}: {e}")

    # Properties & Accessors
    @property
    def is_scheduler_running(self) -> bool:
        return bool(self._data.get("is_scheduler_running", True))

    @is_scheduler_running.setter
    def is_scheduler_running(self, value: bool):
        self._data["is_scheduler_running"] = bool(value)
        self._save()

    @property
    def interval_minutes(self) -> float:
        return float(self._data.get("interval_minutes", 60.0))

    @interval_minutes.setter
    def interval_minutes(self, value: float):
        self._data["interval_minutes"] = max(0.5, float(value))
        self._save()

    @property
    def start_time_str(self) -> str:
        return str(self._data.get("start_time", "09:00"))

    @property
    def end_time_str(self) -> str:
        return str(self._data.get("end_time", "21:00"))

    def set_time_window(self, start_str: str, end_str: str):
        self._data["start_time"] = start_str
        self._data["end_time"] = end_str
        self._save()

    @property
    def timezone_str(self) -> str:
        return str(self._data.get("timezone", "Asia/Tashkent"))

    @property
    def timezone(self) -> pytz.BaseTzInfo:
        try:
            return pytz.timezone(self.timezone_str)
        except Exception:
            return pytz.UTC

    @property
    def message_index(self) -> int:
        return int(self._data.get("message_index", 0))

    @message_index.setter
    def message_index(self, value: int):
        self._data["message_index"] = max(0, int(value))
        self._save()

    @property
    def sticker_enabled(self) -> bool:
        return bool(self._data.get("sticker_enabled", False))

    @sticker_enabled.setter
    def sticker_enabled(self, value: bool):
        self._data["sticker_enabled"] = bool(value)
        self._save()

    @property
    def current_sticker_set(self) -> Optional[str]:
        return self._data.get("current_sticker_set")

    @current_sticker_set.setter
    def current_sticker_set(self, value: Optional[str]):
        self._data["current_sticker_set"] = value
        self._save()

    @property
    def sticker_index(self) -> int:
        return int(self._data.get("sticker_index", 0))

    @sticker_index.setter
    def sticker_index(self, value: int):
        self._data["sticker_index"] = max(0, int(value))
        self._save()

    @property
    def next_run_timestamp(self) -> Optional[float]:
        return self._data.get("next_run_timestamp")

    @next_run_timestamp.setter
    def next_run_timestamp(self, ts: Optional[float]):
        self._data["next_run_timestamp"] = ts
        self._save()

    @property
    def last_run_timestamp(self) -> Optional[float]:
        return self._data.get("last_run_timestamp")

    @last_run_timestamp.setter
    def last_run_timestamp(self, ts: Optional[float]):
        self._data["last_run_timestamp"] = ts
        self._save()

    @property
    def min_delay_between_groups(self) -> int:
        return int(self._data.get("min_delay_between_groups", 3))

    @property
    def max_delay_between_groups(self) -> int:
        return int(self._data.get("max_delay_between_groups", 5))

    def set_delays(self, min_delay: int, max_delay: int):
        self._data["min_delay_between_groups"] = max(1, int(min_delay))
        self._data["max_delay_between_groups"] = max(self._data["min_delay_between_groups"], int(max_delay))
        self._save()

    def get_parsed_window(self) -> Tuple[time, time]:
        """Returns (start_time, end_time) as datetime.time objects."""
        s_parts = self.start_time_str.split(":")
        e_parts = self.end_time_str.split(":")
        start_t = time(hour=int(s_parts[0]), minute=int(s_parts[1]))
        end_t = time(hour=int(e_parts[0]), minute=int(e_parts[1]))
        return start_t, end_t

    def is_within_operating_hours(self) -> Tuple[bool, int]:
        """
        Checks if current local time is inside active hours window.
        Returns: (is_within: bool, seconds_until_start: int)
        """
        tz = self.timezone
        now_dt = datetime.now(tz)
        current_time = now_dt.time()
        start_t, end_t = self.get_parsed_window()

        is_open = False
        if start_t <= end_t:
            is_open = start_t <= current_time <= end_t
        else:
            is_open = current_time >= start_t or current_time <= end_t

        if is_open:
            return True, 0

        target_date = now_dt.date()
        if start_t <= end_t:
            if current_time > end_t:
                target_date += timedelta(days=1)
        else:
            if end_t < current_time < start_t:
                target_date = now_dt.date()

        next_start_dt = tz.localize(datetime.combine(target_date, start_t))
        seconds_until = max(1, int((next_start_dt - now_dt).total_seconds()))
        return False, seconds_until


# Global bot state singleton
state = BotState()
