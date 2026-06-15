import logging
import json
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Timestamp formatted to YYYY-MM-DDTHH:MM:SS
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%dT%H:%M:%S")

        # Context fields
        node_id = getattr(record, "node_id", "unknown")
        component = getattr(record, "component", "unknown")
        event = getattr(record, "event", "generic")

        # Standard LogRecord attributes to ignore when gathering extra kwargs
        standard_attrs = {
            'args', 'asctime', 'created', 'exc_info', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs', 'message',
            'msg', 'name', 'pathname', 'process', 'processName',
            'relativeCreated', 'stack_info', 'thread', 'threadName',
            'node_id', 'component', 'event', 'extra_data'
        }

        extra_data = {}

        # Add explicit extra_data if passed
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            extra_data.update(record.extra_data)

        # Extract extra properties from custom logging attributes
        for key, val in record.__dict__.items():
            if key not in standard_attrs and not key.startswith('_'):
                extra_data[key] = val

        # Handle exception information if present
        if record.exc_info:
            extra_data["exc_info"] = self.formatException(record.exc_info)

        # JSON response object
        log_data = {
            "timestamp": ts_str,
            "ts": ts_str,  # Alias to support example format
            "level": record.levelname,
            "node_id": node_id,
            "node": node_id,  # Alias to support example format
            "component": component,
            "event": event,
            "message": record.getMessage(),
            "extra_data": extra_data,
        }

        # Flatten extra data to top-level object
        for key, val in extra_data.items():
            if key not in log_data:
                log_data[key] = val

        return json.dumps(log_data)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = self.extra.copy() if self.extra else {}
        
        # Merge extra parameters passed in the log call
        if "extra" in kwargs:
            user_extra = kwargs["extra"]
            if isinstance(user_extra, dict):
                # Handle event passed as a key inside extra dict
                if "event" in user_extra:
                    extra["event"] = user_extra["event"]
                extra.update(user_extra)

        if "event" not in extra:
            extra["event"] = "generic"

        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(component: str, node_id: str = "master") -> StructuredLoggerAdapter:
    """
    Creates and returns a structured logger adapter bound to node_id and component.
    """
    logger = logging.getLogger(f"minicloud.{node_id}.{component}")
    logger.setLevel(logging.INFO)

    # Clean existing handlers to avoid duplicates on re-calls
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    return StructuredLoggerAdapter(logger, {"node_id": node_id, "component": component})
