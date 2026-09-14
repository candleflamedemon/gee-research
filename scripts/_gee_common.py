"""Shared, credential-safe utilities for gee-research command-line helpers."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any


_SECRET_PATTERNS = (
    (
        re.compile(
            r"(?i)(access_token|refresh_token|id_token|client_secret|private_key|"
            r"password|passwd)\s*[:=]\s*[^\s,;]+"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"ya29\.[A-Za-z0-9._-]+"), "[REDACTED_OAUTH_TOKEN]"),
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "[REDACTED_API_KEY]"),
    (
        re.compile(
            r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
)

_SENSITIVE_OUTPUT_KEY = re.compile(
    r"(?i)^(?:access[_-]?token|refresh[_-]?token|id[_-]?token|client[_-]?secret|"
    r"private[_-]?key|password|passwd|authorization|credentials?)$"
)

PROJECT_CONFIG_FILENAME = ".gee-project.json"
_SENSITIVE_CONFIG_KEY = re.compile(
    r"(?i)(credential|token|password|passwd|private.?key|client.?secret|service.?account)"
)


class ProjectConfigError(ValueError):
    """Raised when the local project selector is missing, unsafe, or malformed."""


@dataclass(frozen=True)
class ProjectSelection:
    """A non-secret record of how an Earth Engine project was selected."""

    selected_project: str | None
    selection_source: str
    config_path: str | None
    config_exists: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_project": self.selected_project,
            "selection_source": self.selection_source,
            "config_path": self.config_path,
            "config_exists": self.config_exists,
        }


def redact_text(value: Any) -> str:
    text = str(value)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if _SENSITIVE_OUTPUT_KEY.fullmatch(str(key))
                else json_safe(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def print_json(value: Any) -> None:
    print(json.dumps(json_safe(value), ensure_ascii=False, indent=2, default=str))


def package_version() -> str | None:
    try:
        return metadata.version("earthengine-api")
    except metadata.PackageNotFoundError:
        return None


def import_ee():
    try:
        import ee  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "earthengine-api is not installed in this Python environment"
        ) from exc
    return ee


def _clean_project(value: Any, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{source} must provide a non-empty project string")
    project = value.strip()
    if any(character.isspace() for character in project):
        raise ProjectConfigError(f"{source} project must not contain whitespace")
    return project


def resolve_project(
    project: str | None = None,
    *,
    config_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> ProjectSelection:
    """Resolve explicit/config selection without reading Earth Engine credentials.

    The implicit config is only ``.gee-project.json`` in the current working
    project directory. Parent directories are deliberately not searched.
    """
    root = Path(cwd) if cwd is not None else Path.cwd()
    path = Path(config_path) if config_path is not None else root / PROJECT_CONFIG_FILENAME

    if project is not None:
        return ProjectSelection(
            selected_project=_clean_project(project, "explicit argument"),
            selection_source="explicit_argument",
            config_path=str(path),
            config_exists=path.is_file(),
        )

    if not path.exists():
        if config_path is not None:
            raise ProjectConfigError(f"Project config file does not exist: {path}")
        return ProjectSelection(
            selected_project=None,
            selection_source="earth_engine_default",
            config_path=str(path),
            config_exists=False,
        )
    if not path.is_file():
        raise ProjectConfigError(f"Project config path is not a file: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProjectConfigError(f"Could not read valid JSON from project config: {path}") from exc
    if not isinstance(payload, dict):
        raise ProjectConfigError("Project config must be a JSON object")

    sensitive_keys = [str(key) for key in payload if _SENSITIVE_CONFIG_KEY.search(str(key))]
    if sensitive_keys:
        raise ProjectConfigError(
            "Project config must contain only non-secret project selection metadata; "
            "credential-like keys are not allowed"
        )
    selected = _clean_project(payload.get("project"), f"project config {path}")
    return ProjectSelection(
        selected_project=selected,
        selection_source="project_config",
        config_path=str(path),
        config_exists=True,
    )


def effective_project(ee: Any, requested_project: str | None = None) -> dict[str, Any]:
    """Read the non-secret project recorded in initialized Earth Engine client state."""
    project = None
    source = None
    try:
        state_getter = getattr(ee.data, "_get_state", None)
        if callable(state_getter):
            project = getattr(state_getter(), "cloud_api_user_project", None)
            if project:
                source = "earth_engine_client_state"
    except Exception:
        project = None

    if not project:
        project = getattr(ee.data, "_cloud_api_user_project", None)
        if project:
            source = "earth_engine_client_state_legacy"
    if not project and requested_project:
        project = requested_project
        source = "selected_project_unverified"

    return {
        "effective_project": str(project) if project else None,
        "effective_project_source": source,
    }


def initialize_ee(
    ee: Any,
    project: str | None = None,
    *,
    config_path: str | Path | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Initialize using explicit project, local config, then EE's current default."""
    selection = resolve_project(project, config_path=config_path, cwd=cwd)
    if selection.selected_project:
        ee.Initialize(project=selection.selected_project)
    else:
        ee.Initialize()

    details = selection.as_dict()
    details.update(effective_project(ee, selection.selected_project))
    if not details["effective_project"] and selection.selection_source == "earth_engine_default":
        details["needs_user_project"] = True
    else:
        details["needs_user_project"] = False
    return details


def error_payload(stage: str, exc: BaseException) -> dict[str, Any]:
    return {
        "ok": False,
        "stage": stage,
        "error_type": type(exc).__name__,
        "message": redact_text(exc),
    }


def iso_from_millis(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def exit_with_error(stage: str, exc: BaseException, code: int = 1) -> None:
    print_json(error_payload(stage, exc))
    raise SystemExit(code)


def python_summary() -> dict[str, Any]:
    return {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "prefix": sys.prefix,
    }
