import json
from typing import Any, Dict, List, Optional, Union

from logcenter_sdk import LogCenterConfig, LogCenterSender
from infrastructure.config import settings


def _make_sender() -> LogCenterSender:
    cfg = LogCenterConfig(
        base_url=(settings.LOG_API or "").rstrip("/"),
        project_id=settings.LOG_PROJECT_ID or "",
        api_key=settings.LOG_API_KEY,
        enabled=bool(settings.LOG_API and settings.LOG_PROJECT_ID),
    )
    return LogCenterSender(cfg)


sender: LogCenterSender = _make_sender()


def _to_data(additional: Union[str, Dict[str, Any], None]) -> Optional[Dict[str, Any]]:
    if not additional:
        return None
    if isinstance(additional, dict):
        return additional
    try:
        parsed = json.loads(additional)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    return {"additional": additional}


class LogSender:
    def log(self, message: str, *, additional: Union[str, Dict[str, Any], None] = None, status: Optional[str] = None, tags: Optional[List[str]] = None) -> None:
        sender.send_sync("DEBUG", message, data=_to_data(additional), status=status, tags=tags)
