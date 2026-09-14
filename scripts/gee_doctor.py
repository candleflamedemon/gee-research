#!/usr/bin/env python3
"""Diagnose Earth Engine Python access without starting an authentication flow."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
from pathlib import Path
from typing import Any

from _gee_common import (
    ProjectConfigError,
    effective_project,
    initialize_ee,
    json_safe,
    package_version,
    print_json,
    python_summary,
    redact_text,
    resolve_project,
)


PUBLIC_DATASET_ID = "USGS/SRTMGL1_003"
CHECK_ORDER = (
    "python",
    "earthengine_api",
    "ee_import",
    "authentication",
    "initialization",
    "effective_project",
    "server_computation",
    "public_dataset",
    "asset_access",
)
OAUTH_ACTION = (
    "需要用户本人执行 Google OAuth 授权。请在当前 Python 环境中运行 "
    "`earthengine authenticate`，或由用户本人交互执行 `ee.Authenticate()`，然后重试。"
    "本脚本不会自动启动、绕过或代替 Google 身份认证。"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Google Cloud project passed to ee.Initialize().")
    parser.add_argument(
        "--project-config",
        help=(
            "Optional JSON project config path. If omitted, use .gee-project.json "
            "in the current working directory when present."
        ),
    )
    parser.add_argument("--asset-id", help="Optional Earth Engine Asset ID to inspect.")
    parser.add_argument(
        "--public-dataset-id",
        default=PUBLIC_DATASET_ID,
        help=f"Public ee.Image used for the access probe (default: {PUBLIC_DATASET_ID}).",
    )
    parser.add_argument(
        "--no-initialize",
        action="store_true",
        help="Run local Python/package/import checks only; make no Earth Engine request.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Diagnostic output format (default: json).",
    )
    return parser


def check(
    status: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "message": message}
    if details:
        result["details"] = details
    if action:
        result["action"] = action
    return result


def safe_is_file(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.is_file()
    except OSError:
        return False


def credential_hints() -> dict[str, Any]:
    """Check only credential-source presence; never open any credential file."""
    earthengine_path = Path.home() / ".config" / "earthengine" / "credentials"

    adc_candidates: set[Path] = set()
    cloud_config = os.environ.get("CLOUDSDK_CONFIG")
    appdata = os.environ.get("APPDATA")
    if cloud_config:
        adc_candidates.add(Path(cloud_config) / "application_default_credentials.json")
    if appdata:
        adc_candidates.add(Path(appdata) / "gcloud" / "application_default_credentials.json")
    adc_candidates.add(
        Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    )
    adc_candidates.add(
        Path.home()
        / "AppData"
        / "Roaming"
        / "gcloud"
        / "application_default_credentials.json"
    )

    application_credentials = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    application_credentials_path = (
        Path(application_credentials) if application_credentials else None
    )
    return {
        "earth_engine_credentials_file_exists": safe_is_file(earthengine_path),
        "application_default_credentials_file_exists": any(
            safe_is_file(path) for path in adc_candidates
        ),
        "google_application_credentials_env_set": bool(application_credentials),
        "google_application_credentials_target_exists": safe_is_file(
            application_credentials_path
        ),
        "credential_files_opened_by_script": False,
    }


def safe_error(exc: BaseException) -> dict[str, str]:
    """Return a useful bounded error while defensively removing secret-shaped text."""
    message = redact_text(exc)
    patterns = (
        (
            re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"),
            r"\1[REDACTED]",
        ),
        (
            re.compile(
                r"(?i)([\"']?(?:access|refresh|id)_?token[\"']?\s*[:=]\s*[\"']?)"
                r"[^\"',\s}]+"
            ),
            r"\1[REDACTED]",
        ),
        (
            re.compile(r"(?i)([\"']?client_secret[\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+"),
            r"\1[REDACTED]",
        ),
        (
            re.compile(r"(?i)([\"']?(?:password|passwd)[\"']?\s*[:=]\s*[\"']?)[^\"',\s}]+"),
            r"\1[REDACTED]",
        ),
    )
    for pattern, replacement in patterns:
        message = pattern.sub(replacement, message)
    if len(message) > 2000:
        message = message[:2000] + "…[truncated]"
    return {"type": type(exc).__name__, "message": message}


def classify_initialization_error(exc: BaseException) -> str:
    if isinstance(exc, ProjectConfigError):
        return "project"
    text = str(exc).lower()
    authentication_markers = (
        "please authorize access",
        "default credentials were not found",
        "could not automatically determine credentials",
        "invalid_grant",
        "invalid credentials",
        "unauthenticated",
        "authentication credentials",
        "refresh token",
        "reauth",
    )
    project_markers = (
        "no project found",
        "quota project",
        "project is required",
        "has not been used in project",
        "api has not been used in project",
        "not registered for earth engine",
        "required permission to use project",
    )
    network_markers = (
        "connection",
        "timed out",
        "timeout",
        "name resolution",
        "proxy",
        "ssl",
        "network",
    )
    if any(marker in text for marker in authentication_markers):
        return "authentication"
    if any(marker in text for marker in project_markers):
        return "project"
    if any(marker in text for marker in network_markers):
        return "network"
    if "permission_denied" in text or "permission denied" in text or "403" in text:
        return "permission"
    return "unknown"


def asset_summary(asset: Any) -> dict[str, Any]:
    """Return bounded structural metadata, excluding user-authored properties."""
    if not isinstance(asset, dict):
        return {"metadata_type": type(asset).__name__}
    core_fields = (
        "name",
        "id",
        "type",
        "startTime",
        "endTime",
        "createTime",
        "updateTime",
        "sizeBytes",
    )
    summary = {key: asset.get(key) for key in core_fields if key in asset}
    bands = asset.get("bands")
    if isinstance(bands, list):
        summary["band_count"] = len(bands)
        summary["band_names"] = [
            band.get("id")
            for band in bands[:100]
            if isinstance(band, dict) and band.get("id") is not None
        ]
    if "properties" in asset and isinstance(asset.get("properties"), dict):
        summary["property_count"] = len(asset["properties"])
        summary["properties_included"] = False
    return summary


def skipped(message: str) -> dict[str, Any]:
    return check("skip", message)


def complete_report(
    report: dict[str, Any], checks: dict[str, dict[str, Any]], operational: bool | None
) -> dict[str, Any]:
    ordered = [{"id": name, **checks[name]} for name in CHECK_ORDER]
    counts = {
        status: sum(item["status"] == status for item in ordered)
        for status in ("pass", "fail", "warn", "skip")
    }
    report["checks"] = ordered
    report["summary"] = counts
    report["operational"] = operational
    report["ok"] = counts["fail"] == 0
    return report


def emit(report: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print_json(report)
        return

    safe_report = json_safe(report)
    print("GEE Doctor diagnostic")
    print(f"Overall: {'PASS' if safe_report['ok'] else 'FAIL'}")
    if safe_report["operational"] is None:
        print("Earth Engine operational status: NOT TESTED")
    else:
        print(
            "Earth Engine operational status: "
            + ("AVAILABLE" if safe_report["operational"] else "UNAVAILABLE")
        )
    for item in safe_report["checks"]:
        print(f"[{item['status'].upper():4}] {item['id']}: {item['message']}")
        if item.get("details"):
            print("       " + json.dumps(item["details"], ensure_ascii=False, default=str))
        if item.get("action"):
            print("       Next: " + item["action"])
    print(
        "Security: credential files were not opened by this script; no token, "
        "password, private key, or credential content is included in the report."
    )


def finish(
    report: dict[str, Any],
    checks: dict[str, dict[str, Any]],
    output_format: str,
    *,
    operational: bool | None,
    exit_code: int,
) -> int:
    emit(complete_report(report, checks, operational), output_format)
    return exit_code


def main() -> int:
    args = build_parser().parse_args()
    hints = credential_hints()
    report: dict[str, Any] = {
        "schema_version": 1,
        "mode": "local_only" if args.no_initialize else "operational",
        "security": {
            "authentication_flow_started": False,
            "credential_files_opened_by_script": False,
            "credential_contents_reported": False,
            "secrets_reported": False,
            "note": (
                "The script checks credential-source presence only. ee.Initialize() may "
                "securely load existing operating-system credentials."
            ),
        },
    }
    checks: dict[str, dict[str, Any]] = {}
    python = python_summary()
    checks["python"] = check(
        "pass", f"Python {python['version']} is running.", details=python
    )

    installed_version = package_version()
    try:
        ee = importlib.import_module("ee")
    except Exception as exc:
        error = safe_error(exc)
        if installed_version:
            checks["earthengine_api"] = check(
                "pass",
                f"earthengine-api {installed_version} distribution is installed.",
                details={"version": installed_version},
            )
        else:
            checks["earthengine_api"] = check(
                "fail",
                "earthengine-api is not installed in this Python environment.",
                action="Install earthengine-api into this exact environment, then rerun.",
            )
        checks["ee_import"] = check(
            "fail", "The ee module could not be imported.", details={"error": error}
        )
        checks["authentication"] = check(
            "skip",
            "Authentication cannot be verified until the ee module imports.",
            details=hints,
        )
        for name in CHECK_ORDER[4:8]:
            checks[name] = skipped("Skipped because the ee module did not import.")
        checks["asset_access"] = skipped(
            "Skipped because the ee module did not import."
            if args.asset_id
            else "No Asset ID was supplied."
        )
        return finish(report, checks, args.format, operational=False, exit_code=2)

    module_version = getattr(ee, "__version__", None)
    module_file = getattr(ee, "__file__", None)
    if installed_version:
        checks["earthengine_api"] = check(
            "pass",
            f"earthengine-api {installed_version} is installed.",
            details={"version": installed_version},
        )
    else:
        checks["earthengine_api"] = check(
            "warn",
            "The ee module imports, but earthengine-api package metadata is unavailable.",
        )
    checks["ee_import"] = check(
        "pass",
        "The ee module imported successfully.",
        details={"module_version": module_version, "module_file": module_file},
    )

    if args.no_initialize:
        selection_error = None
        try:
            local_selection = resolve_project(
                args.project, config_path=args.project_config
            ).as_dict()
            report["project_selection"] = local_selection
        except Exception as exc:
            selection_error = safe_error(exc)
            report["project_selection"] = {
                "selection_source": "invalid",
                "error": selection_error,
            }
        checks["authentication"] = check(
            "warn",
            "Credential-source presence was checked, but authentication was not verified.",
            details=hints,
        )
        checks["initialization"] = skipped("Disabled by --no-initialize.")
        if selection_error:
            checks["effective_project"] = check(
                "fail",
                "The local Project selection is invalid.",
                details={"error": selection_error},
                action="Fix or remove the reported Project config, then retry.",
            )
        else:
            checks["effective_project"] = skipped(
                "Selection source inspected locally; effective Project requires ee.Initialize()."
            )
        checks["server_computation"] = skipped("Disabled by --no-initialize.")
        checks["public_dataset"] = skipped("Disabled by --no-initialize.")
        checks["asset_access"] = skipped(
            "Disabled by --no-initialize."
            if args.asset_id
            else "No Asset ID was supplied."
        )
        return finish(
            report,
            checks,
            args.format,
            operational=None,
            exit_code=2 if selection_error else 0,
        )

    try:
        local_selection = resolve_project(
            args.project, config_path=args.project_config
        )
        report["project_selection"] = local_selection.as_dict()
        project_selection = initialize_ee(
            ee, args.project, config_path=args.project_config
        )
        report["project_selection"] = project_selection
    except Exception as exc:
        category = classify_initialization_error(exc)
        error = safe_error(exc)
        if category == "authentication":
            checks["authentication"] = check(
                "fail",
                "Existing Earth Engine authentication was not accepted.",
                details={**hints, "error_category": category},
                action=OAUTH_ACTION,
            )
        else:
            checks["authentication"] = check(
                "warn",
                "Authentication could not be proven because initialization failed for another or unknown reason.",
                details={**hints, "error_category": category},
            )
        checks["initialization"] = check(
            "fail",
            "ee.Initialize() failed.",
            details={"error_category": category, "error": error},
            action=(
                OAUTH_ACTION
                if category == "authentication"
                else "Check the reported project, permissions, API registration, and network, then retry."
            ),
        )
        checks["effective_project"] = check(
            "skip",
            "No effective project could be confirmed because initialization failed.",
            details={
                "project_argument": args.project,
                "project_config": args.project_config,
            },
        )
        checks["server_computation"] = skipped("Requires successful ee.Initialize().")
        checks["public_dataset"] = skipped("Requires successful ee.Initialize().")
        checks["asset_access"] = skipped(
            "Requires successful ee.Initialize()."
            if args.asset_id
            else "No Asset ID was supplied."
        )
        return finish(report, checks, args.format, operational=False, exit_code=3)

    checks["authentication"] = check(
        "pass",
        "Existing operating-system credentials were accepted by ee.Initialize().",
        details=hints,
    )
    checks["initialization"] = check("pass", "ee.Initialize() succeeded.")

    project = effective_project(ee, project_selection.get("selected_project"))
    project.update(
        {
            "selection_source": project_selection.get("selection_source"),
            "config_path": project_selection.get("config_path"),
        }
    )
    if project["effective_project"]:
        checks["effective_project"] = check(
            "pass",
            f"Effective Earth Engine project: {project['effective_project']}",
            details=project,
        )
    else:
        checks["effective_project"] = check(
            "warn",
            "Initialization succeeded, but the effective project could not be determined; ask the user before project-sensitive work.",
            details=project,
        )

    try:
        server_value = ee.Number(1).add(1).getInfo()
        if server_value != 2:
            raise RuntimeError(f"Unexpected server result: {server_value!r}")
        checks["server_computation"] = check(
            "pass",
            "A minimal server-side computation succeeded.",
            details={"expression": "ee.Number(1).add(1)", "result": server_value},
        )
    except Exception as exc:
        checks["server_computation"] = check(
            "fail",
            "The minimal server-side computation failed.",
            details={"error": safe_error(exc)},
        )
        checks["public_dataset"] = skipped(
            "Skipped after the server computation failed."
        )
        checks["asset_access"] = skipped(
            "Skipped after the server computation failed."
            if args.asset_id
            else "No Asset ID was supplied."
        )
        return finish(report, checks, args.format, operational=False, exit_code=4)

    try:
        band_names = ee.Image(args.public_dataset_id).bandNames().getInfo()
        if not isinstance(band_names, list) or not band_names:
            raise RuntimeError("The public dataset returned no bands.")
        checks["public_dataset"] = check(
            "pass",
            "A public Earth Engine dataset is accessible.",
            details={
                "dataset_id": args.public_dataset_id,
                "band_count": len(band_names),
                "band_names": band_names[:100],
            },
        )
    except Exception as exc:
        checks["public_dataset"] = check(
            "fail",
            "The public Earth Engine dataset probe failed.",
            details={
                "dataset_id": args.public_dataset_id,
                "error": safe_error(exc),
            },
        )

    if args.asset_id:
        try:
            asset = ee.data.getAsset(args.asset_id)
            checks["asset_access"] = check(
                "pass",
                "The requested Asset exists and is accessible.",
                details={
                    "requested_asset_id": args.asset_id,
                    "asset": asset_summary(asset),
                },
            )
        except Exception as exc:
            checks["asset_access"] = check(
                "fail",
                "The requested Asset could not be accessed.",
                details={
                    "requested_asset_id": args.asset_id,
                    "error": safe_error(exc),
                },
                action="Verify the Asset ID and the signed-in account's permissions.",
            )
    else:
        checks["asset_access"] = skipped("No Asset ID was supplied.")

    if checks["public_dataset"]["status"] == "fail":
        exit_code = 5
    elif checks["asset_access"]["status"] == "fail":
        exit_code = 6
    else:
        exit_code = 0
    return finish(
        report,
        checks,
        args.format,
        operational=exit_code == 0,
        exit_code=exit_code,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print_json(
            {
                "ok": False,
                "stage": "interrupted",
                "message": "Diagnostic interrupted by user.",
            }
        )
        raise SystemExit(130)
