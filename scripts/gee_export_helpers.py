#!/usr/bin/env python3
"""Build safe Earth Engine export tasks and submit them only when authorized.

The four task builders in this module never call ``task.start()``. Asset
builders first perform a read-only target lookup and never request overwrite or
delete an Asset. Use :func:`start_prepared_task` with ``submit=True`` only
after the user has explicitly asked to submit/start the exact export.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Any, Callable

from _gee_common import print_json, redact_text


_AMBIGUOUS_ASSET_MARKERS = (
    "does not exist or doesn't allow this operation",
    "does not exist or does not allow this operation",
    "not found or permission denied",
    "not found or inaccessible",
)
_NOT_FOUND_ASSET_MARKERS = (
    "not found",
    "does not exist",
    "no such asset",
    "http 404",
    "status 404",
)


class ExportValidationError(ValueError):
    """The requested export parameters are internally inconsistent."""


class AssetConflictError(RuntimeError):
    """The destination Asset already exists and must not be overwritten."""


class AssetTargetCheckError(RuntimeError):
    """The destination Asset could not be verified safely."""


@dataclass(frozen=True)
class PreparedExport:
    """A locally prepared, not-yet-submitted Earth Engine batch task."""

    task: Any
    export_type: str
    destination_kind: str
    destination: str
    description: str
    parameters: dict[str, Any]
    asset_preflight: dict[str, Any] | None = None


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExportValidationError(f"{label} is required")
    return value


def _validate_positive(value: int | float | None, label: str) -> None:
    if value is not None and (isinstance(value, bool) or value <= 0):
        raise ExportValidationError(f"{label} must be positive")


def _validate_priority(priority: int | None) -> None:
    if priority is not None and (
        isinstance(priority, bool)
        or not isinstance(priority, int)
        or not 0 <= priority <= 9999
    ):
        raise ExportValidationError("priority must be an integer between 0 and 9999")


def _validate_dimensions(dimensions: int | str | None) -> None:
    if dimensions is None:
        return
    if isinstance(dimensions, bool):
        raise ExportValidationError("dimensions must be a positive integer or WIDTHxHEIGHT")
    if isinstance(dimensions, int):
        if dimensions <= 0:
            raise ExportValidationError("dimensions must be positive")
        return
    if isinstance(dimensions, str) and re.fullmatch(r"[1-9]\d*[xX][1-9]\d*", dimensions):
        return
    raise ExportValidationError("dimensions must be a positive integer or WIDTHxHEIGHT")


def _validate_image_grid(
    *,
    dimensions: int | str | None,
    scale: float | None,
    crs: str | None,
    crs_transform: Any | None,
    max_pixels: int | None,
) -> None:
    _validate_dimensions(dimensions)
    _validate_positive(scale, "scale")
    _validate_positive(max_pixels, "maxPixels")
    selected = sum(value is not None for value in (dimensions, scale, crs_transform))
    if selected > 1:
        raise ExportValidationError(
            "dimensions, scale, and crsTransform are mutually exclusive"
        )
    if crs_transform is not None and not crs:
        raise ExportValidationError("crsTransform requires crs")


def _validate_file_dimensions(
    file_dimensions: int | list[int] | tuple[int, int] | None,
    shard_size: int | None,
) -> None:
    _validate_positive(shard_size, "shardSize")
    if file_dimensions is None:
        return
    if isinstance(file_dimensions, bool):
        raise ExportValidationError("fileDimensions must contain positive integers")
    values = (file_dimensions,) if isinstance(file_dimensions, int) else tuple(file_dimensions)
    if (
        len(values) not in {1, 2}
        or any(
            isinstance(item, bool) or not isinstance(item, int) or item <= 0
            for item in values
        )
    ):
        raise ExportValidationError(
            "fileDimensions must be a positive integer or a two-integer tuple"
        )
    if shard_size is not None and any(item % shard_size for item in values):
        raise ExportValidationError("fileDimensions must be a multiple of shardSize")


def _validate_max_vertices(max_vertices: int | None) -> None:
    _validate_positive(max_vertices, "maxVertices")


def _compact_kwargs(**values: Any) -> dict[str, Any]:
    """Omit None so Earth Engine, not this helper, owns API defaults."""
    return {key: value for key, value in values.items() if value is not None}


def _asset_failure_kind(exc: BaseException) -> str:
    message = redact_text(exc).lower()
    if any(marker in message for marker in _AMBIGUOUS_ASSET_MARKERS):
        return "ambiguous"
    if any(marker in message for marker in _NOT_FOUND_ASSET_MARKERS):
        return "not_found"
    return "other"


def check_asset_destination(
    ee_module: Any,
    asset_id: str,
    *,
    allow_unverified_target: bool = False,
    asset_lookup: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Check an Asset destination without deleting or modifying anything.

    Some Earth Engine responses deliberately combine not-found and
    permission-denied. Those responses are blocked by default. A caller may opt
    into task construction with ``allow_unverified_target=True`` only after
    separately checking the exact destination and parent permissions. Even in
    that mode the export builders always pass ``overwrite=False``.
    """
    asset_id = _require_text(asset_id, "assetId")
    lookup = asset_lookup or ee_module.data.getAsset
    try:
        asset = lookup(asset_id)
    except Exception as exc:
        kind = _asset_failure_kind(exc)
        if kind == "not_found":
            return {"asset_id": asset_id, "exists": False, "status": "AVAILABLE"}
        if kind == "ambiguous" and allow_unverified_target:
            return {
                "asset_id": asset_id,
                "exists": None,
                "status": "NOT_FOUND_OR_INACCESSIBLE_ALLOWED",
                "warning": (
                    "Earth Engine could not distinguish a missing Asset from an "
                    "inaccessible one; overwrite remains disabled."
                ),
            }
        if kind == "ambiguous":
            raise AssetTargetCheckError(
                "Earth Engine could not verify whether the destination Asset is missing "
                f"or inaccessible: {asset_id}. Inspect the exact target and parent "
                "permissions; then retry with allow_unverified_target=True only if appropriate."
            ) from exc
        raise AssetTargetCheckError(
            f"Could not verify destination Asset {asset_id}: {redact_text(exc)}"
        ) from exc

    if asset is not None:
        asset_type = asset.get("type") if isinstance(asset, dict) else None
        raise AssetConflictError(
            f"Destination Asset already exists and will not be overwritten: {asset_id}"
            + (f" (type={asset_type})" if asset_type else "")
        )
    return {"asset_id": asset_id, "exists": False, "status": "AVAILABLE"}


def _image_parameters(
    *,
    region: Any | None,
    scale: float | None,
    crs: str | None,
    crs_transform: Any | None,
    dimensions: int | str | None,
    max_pixels: int | None,
) -> dict[str, Any]:
    return {
        "region_supplied": region is not None,
        "scale": scale,
        "crs": crs,
        "crs_transform_supplied": crs_transform is not None,
        "dimensions": dimensions,
        "max_pixels": max_pixels,
    }


def create_image_to_asset_task(
    image: Any,
    *,
    description: str,
    asset_id: str,
    region: Any | None = None,
    scale: float | None = None,
    crs: str | None = None,
    crs_transform: Any | None = None,
    dimensions: int | str | None = None,
    max_pixels: int | None = None,
    pyramiding_policy: dict[str, str] | None = None,
    priority: int | None = None,
    allow_unverified_target: bool = False,
    ee_module: Any | None = None,
) -> PreparedExport:
    """Prepare ``ee.batch.Export.image.toAsset`` without submitting it."""
    description = _require_text(description, "description")
    asset_id = _require_text(asset_id, "assetId")
    _validate_image_grid(
        dimensions=dimensions,
        scale=scale,
        crs=crs,
        crs_transform=crs_transform,
        max_pixels=max_pixels,
    )
    _validate_priority(priority)
    if ee_module is None:
        import ee as ee_module  # type: ignore
    preflight = check_asset_destination(
        ee_module,
        asset_id,
        allow_unverified_target=allow_unverified_target,
    )
    kwargs = _compact_kwargs(
        image=image,
        description=description,
        assetId=asset_id,
        pyramidingPolicy=pyramiding_policy,
        dimensions=dimensions,
        region=region,
        scale=scale,
        crs=crs,
        crsTransform=crs_transform,
        maxPixels=max_pixels,
        priority=priority,
    )
    kwargs["overwrite"] = False
    task = ee_module.batch.Export.image.toAsset(**kwargs)
    return PreparedExport(
        task=task,
        export_type="image",
        destination_kind="asset",
        destination=asset_id,
        description=description,
        parameters={
            **_image_parameters(
                region=region,
                scale=scale,
                crs=crs,
                crs_transform=crs_transform,
                dimensions=dimensions,
                max_pixels=max_pixels,
            ),
            "pyramiding_policy_supplied": pyramiding_policy is not None,
            "priority": priority,
            "overwrite": False,
        },
        asset_preflight=preflight,
    )


def create_image_to_drive_task(
    image: Any,
    *,
    description: str,
    folder: str | None = None,
    file_name_prefix: str | None = None,
    region: Any | None = None,
    scale: float | None = None,
    crs: str | None = None,
    crs_transform: Any | None = None,
    dimensions: int | str | None = None,
    max_pixels: int | None = None,
    shard_size: int | None = None,
    file_dimensions: int | list[int] | tuple[int, int] | None = None,
    skip_empty_tiles: bool | None = None,
    file_format: str | None = None,
    format_options: dict[str, Any] | None = None,
    priority: int | None = None,
    ee_module: Any | None = None,
) -> PreparedExport:
    """Prepare ``ee.batch.Export.image.toDrive`` without submitting it."""
    description = _require_text(description, "description")
    _validate_image_grid(
        dimensions=dimensions,
        scale=scale,
        crs=crs,
        crs_transform=crs_transform,
        max_pixels=max_pixels,
    )
    _validate_file_dimensions(file_dimensions, shard_size)
    _validate_priority(priority)
    if skip_empty_tiles and file_format not in (None, "GeoTIFF"):
        raise ExportValidationError("skipEmptyTiles is supported only for GeoTIFF exports")
    if ee_module is None:
        import ee as ee_module  # type: ignore
    kwargs = _compact_kwargs(
        image=image,
        description=description,
        folder=folder,
        fileNamePrefix=file_name_prefix,
        dimensions=dimensions,
        region=region,
        scale=scale,
        crs=crs,
        crsTransform=crs_transform,
        maxPixels=max_pixels,
        shardSize=shard_size,
        fileDimensions=file_dimensions,
        skipEmptyTiles=skip_empty_tiles,
        fileFormat=file_format,
        formatOptions=format_options,
        priority=priority,
    )
    task = ee_module.batch.Export.image.toDrive(**kwargs)
    destination = f"Drive folder: {folder}" if folder else "Google Drive root"
    return PreparedExport(
        task=task,
        export_type="image",
        destination_kind="drive",
        destination=destination,
        description=description,
        parameters={
            **_image_parameters(
                region=region,
                scale=scale,
                crs=crs,
                crs_transform=crs_transform,
                dimensions=dimensions,
                max_pixels=max_pixels,
            ),
            "folder": folder,
            "file_name_prefix": file_name_prefix,
            "file_format": file_format,
            "priority": priority,
        },
    )


def create_table_to_asset_task(
    collection: Any,
    *,
    description: str,
    asset_id: str,
    max_vertices: int | None = None,
    priority: int | None = None,
    allow_unverified_target: bool = False,
    ee_module: Any | None = None,
) -> PreparedExport:
    """Prepare ``ee.batch.Export.table.toAsset`` without submitting it."""
    description = _require_text(description, "description")
    asset_id = _require_text(asset_id, "assetId")
    _validate_max_vertices(max_vertices)
    _validate_priority(priority)
    if ee_module is None:
        import ee as ee_module  # type: ignore
    preflight = check_asset_destination(
        ee_module,
        asset_id,
        allow_unverified_target=allow_unverified_target,
    )
    kwargs = _compact_kwargs(
        collection=collection,
        description=description,
        assetId=asset_id,
        maxVertices=max_vertices,
        priority=priority,
    )
    kwargs["overwrite"] = False
    task = ee_module.batch.Export.table.toAsset(**kwargs)
    return PreparedExport(
        task=task,
        export_type="table",
        destination_kind="asset",
        destination=asset_id,
        description=description,
        parameters={
            "max_vertices": max_vertices,
            "priority": priority,
            "overwrite": False,
        },
        asset_preflight=preflight,
    )


def create_table_to_drive_task(
    collection: Any,
    *,
    description: str,
    folder: str | None = None,
    file_name_prefix: str | None = None,
    file_format: str | None = None,
    selectors: list[str] | tuple[str, ...] | str | None = None,
    max_vertices: int | None = None,
    priority: int | None = None,
    ee_module: Any | None = None,
) -> PreparedExport:
    """Prepare ``ee.batch.Export.table.toDrive`` without submitting it."""
    description = _require_text(description, "description")
    _validate_max_vertices(max_vertices)
    _validate_priority(priority)
    if ee_module is None:
        import ee as ee_module  # type: ignore
    kwargs = _compact_kwargs(
        collection=collection,
        description=description,
        folder=folder,
        fileNamePrefix=file_name_prefix,
        fileFormat=file_format,
        selectors=selectors,
        maxVertices=max_vertices,
        priority=priority,
    )
    task = ee_module.batch.Export.table.toDrive(**kwargs)
    destination = f"Drive folder: {folder}" if folder else "Google Drive root"
    return PreparedExport(
        task=task,
        export_type="table",
        destination_kind="drive",
        destination=destination,
        description=description,
        parameters={
            "folder": folder,
            "file_name_prefix": file_name_prefix,
            "file_format": file_format,
            "selectors_supplied": selectors is not None,
            "max_vertices": max_vertices,
            "priority": priority,
        },
    )


def _bounded_task_status(task: Any) -> dict[str, Any]:
    status = task.status()
    if not isinstance(status, dict):
        return {}
    return {
        key: status.get(key)
        for key in (
            "id",
            "name",
            "state",
            "description",
            "task_type",
            "destination_uris",
            "error_message",
        )
        if key in status
    }


def start_prepared_task(
    prepared: PreparedExport | Any,
    *,
    submit: bool = False,
) -> dict[str, Any]:
    """Optionally submit once, then read one initial status without polling.

    ``submit=False`` is the safe default. ``submit=True`` is an explicit code
    gate and must represent the user's instruction to actually export, submit,
    or start this exact task.
    """
    if isinstance(prepared, PreparedExport):
        task = prepared.task
        result: dict[str, Any] = {
            "export_type": prepared.export_type,
            "destination_kind": prepared.destination_kind,
            "destination": prepared.destination,
            "description": prepared.description,
            "parameters": prepared.parameters,
        }
        if prepared.asset_preflight is not None:
            result["asset_preflight"] = prepared.asset_preflight
    else:
        task = prepared
        result = {}

    if submit:
        task.start()

    try:
        status = _bounded_task_status(task)
        status_error = None
    except Exception as exc:
        status = {}
        status_error = redact_text(exc)

    task_id = status.get("id") or status.get("name") or getattr(task, "id", None)
    state = status.get("state") or ("STATUS_UNAVAILABLE" if submit else "UNSUBMITTED")
    result.update(
        {
            "submitted": submit,
            "task_id": task_id,
            "initial_state": state,
            "task": status,
            "status_checked_once": True,
            "waited_for_completion": False,
        }
    )
    if not submit:
        result["reason"] = (
            "submission gate closed; pass submit=True only after explicit user authorization"
        )
    if status_error:
        result["status_error"] = status_error
    return result


__all__ = [
    "AssetConflictError",
    "AssetTargetCheckError",
    "ExportValidationError",
    "PreparedExport",
    "check_asset_destination",
    "create_image_to_asset_task",
    "create_image_to_drive_task",
    "create_table_to_asset_task",
    "create_table_to_drive_task",
    "start_prepared_task",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Describe the safe Earth Engine Export helper contract. Import this module "
            "from research code to build tasks; this CLI never creates or starts a task."
        ),
        epilog=(
            "Python example: create_image_to_drive_task(...), then call "
            "start_prepared_task(prepared) for a non-submitting preview or "
            "start_prepared_task(prepared, submit=True) only after explicit user authorization."
        ),
    )
    parser.add_argument(
        "--show-contract",
        action="store_true",
        help="Print a machine-readable summary of builders and safety gates.",
    )
    args = parser.parse_args()
    if not args.show_contract:
        parser.print_help()
        return 0
    print_json(
        {
            "builders": [
                "create_image_to_asset_task",
                "create_image_to_drive_task",
                "create_table_to_asset_task",
                "create_table_to_drive_task",
            ],
            "default_submitted": False,
            "submission_gate": "start_prepared_task(prepared, submit=True)",
            "asset_overwrite": False,
            "asset_delete_supported": False,
            "waits_for_completion": False,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
