# shared/logger.py
#
# Human-readable console output by default.
# Set  LOG_FORMAT=json  environment variable to switch back to JSON
# (useful for log aggregation / Prometheus in Week 4).

import logging
import json
import os
import sys
from datetime import datetime, timezone

# ── ANSI color codes ─────────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"

_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"
_MAGENTA= "\033[35m"
_BLUE   = "\033[34m"
_WHITE  = "\033[97m"

# Level → color
_LEVEL_COLORS = {
    "DEBUG":    _DIM + _WHITE,
    "INFO":     _GREEN,
    "WARNING":  _YELLOW,
    "ERROR":    _RED,
    "CRITICAL": _BOLD + _RED,
}

# Event keyword → icon
_EVENT_ICONS = {
    "startup":               "🚀",
    "shutdown":              "🛑",
    "registration_started":  "📡",
    "registration_success":  "✅",
    "registration_failed_retry": "🔄",
    "connect_error":         "🔌",
    "timeout_error":         "⏱️ ",
    "beat_sent":             "💓",
    "beat_timeout_error":    "⚠️ ",
    "beat_connect_error":    "🔌",
    "beat_warning":          "⚠️ ",
    "heartbeat_sender_started": "💓",
    "node_dead":             "💀",
    "health_check_done":     "🩺",
    "redis_connected":       "🗄️ ",
    "redis_init_failed":     "⚠️ ",
    "redis_load_success":    "📂",
    "redis_load_error":      "❌",
    "redis_save_error":      "❌",
    "redis_update_error":    "❌",
    "redis_remove_error":    "❌",
    "redis_status_update_error": "❌",
    "health_monitor_error":  "❌",
    "generic":               "ℹ️ ",
}


class PrettyFormatter(logging.Formatter):
    """
    Produces compact, human-readable lines like:

    13:21:05  💓  heartbeat    [fd5d79df]  CPU: 7.1%  RAM: 59.0%
    13:21:05  ✅  registrar    [fd5d79df]  Registered with master
    13:21:05  💀  health_mon   [master]    Node fd5d... is DEAD  (last beat 35s ago)
    """

    def format(self, record: logging.LogRecord) -> str:
        # ── Time ──────────────────────────────────────────────────────────────
        dt  = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts  = dt.strftime("%H:%M:%S")

        # ── Context fields ─────────────────────────────────────────────────
        node_id   = getattr(record, "node_id",   "unknown")
        component = getattr(record, "component", "unknown")
        event     = getattr(record, "event",     "generic")
        level     = record.levelname

        # ── Color + icon ───────────────────────────────────────────────────
        level_color = _LEVEL_COLORS.get(level, _WHITE)
        icon        = _EVENT_ICONS.get(event, "ℹ️ ")

        # Short node label — last 8 chars of UUID is enough to distinguish
        short_id = node_id[-8:] if len(node_id) > 8 else node_id
        node_tag = f"{_DIM}[{short_id}]{_RESET}"

        # Component padded to 12 chars for column alignment
        comp_str  = f"{_CYAN}{component:<12}{_RESET}"

        # ── Message ─────────────────────────────────────────────────────────
        message = record.getMessage()

        # For beat_sent events, extract metrics and make a cleaner line
        cpu = getattr(record, "cpu", None)
        ram = getattr(record, "ram", None)
        if event == "beat_sent" and cpu is not None and ram is not None:
            message = f"CPU: {_BOLD}{cpu:.1f}%{_RESET}  RAM: {_BOLD}{ram:.1f}%{_RESET}"

        # For node_dead, highlight the key number
        secs = getattr(record, "last_beat_seconds_ago", None)
        if event == "node_dead" and secs is not None:
            dead_id = getattr(record, "dead_node_id", node_id)
            message = (
                f"{_BOLD}{_RED}Node [{dead_id[-8:]}] is DEAD{_RESET} "
                f"(last beat {secs:.0f}s ago)"
            )

        # Consecutive failures counter
        cf = getattr(record, "consecutive_failures", None)
        if cf is not None and cf > 0 and event in ("beat_timeout_error", "beat_warning"):
            message = f"{message}  {_DIM}(fail #{cf}){_RESET}"

        # ── Assemble line ──────────────────────────────────────────────────
        line = (
            f"{_DIM}{ts}{_RESET}  "
            f"{icon}  "
            f"{comp_str}  "
            f"{node_tag}  "
            f"{level_color}{message}{_RESET}"
        )

        # ── Exception info ─────────────────────────────────────────────────
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


class JSONFormatter(logging.Formatter):
    """Original JSON formatter — activate with LOG_FORMAT=json."""

    def format(self, record: logging.LogRecord) -> str:
        dt     = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S")

        node_id   = getattr(record, "node_id",   "unknown")
        component = getattr(record, "component", "unknown")
        event     = getattr(record, "event",     "generic")

        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message',
            'msg', 'name', 'pathname', 'process', 'processName',
            'relativeCreated', 'stack_info', 'thread', 'threadName',
            'node_id', 'component', 'event', 'extra_data'
        }

        extra_data = {}
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            extra_data.update(record.extra_data)
        for key, val in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                extra_data[key] = val
        if record.exc_info:
            extra_data["exc_info"] = self.formatException(record.exc_info)

        log_data = {
            "timestamp": ts_str,
            "level":     record.levelname,
            "node_id":   node_id,
            "component": component,
            "event":     event,
            "message":   record.getMessage(),
            "extra":     extra_data,
        }
        return json.dumps(log_data)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = self.extra.copy() if self.extra else {}
        if "extra" in kwargs:
            user_extra = kwargs["extra"]
            if isinstance(user_extra, dict):
                if "event" in user_extra:
                    extra["event"] = user_extra["event"]
                extra.update(user_extra)
        if "event" not in extra:
            extra["event"] = "generic"
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(component: str, node_id: str = "master") -> StructuredLoggerAdapter:
    """
    Returns a structured logger. Output format:
      - Default → pretty colored console output  (human-readable)
      - LOG_FORMAT=json → structured JSON lines   (machine-readable / Week 4)
    """
    logger = logging.getLogger(f"minicloud.{node_id}.{component}")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)

        if os.getenv("LOG_FORMAT", "pretty").lower() == "json":
            handler.setFormatter(JSONFormatter())
        else:
            handler.setFormatter(PrettyFormatter())
            # Only show DEBUG from health_monitor (it's noisy every 5s)
            # Set to INFO to suppress health_check_done debug lines
            logger.setLevel(logging.INFO)

        logger.addHandler(handler)
        logger.propagate = False

    return StructuredLoggerAdapter(logger, {"node_id": node_id, "component": component})
