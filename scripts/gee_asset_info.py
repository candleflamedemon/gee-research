#!/usr/bin/env python3
"""Verify one Earth Engine Asset and return bounded, type-aware metadata."""

from __future__ import annotations

import argparse
from typing import Any

from _gee_common import error_payload, import_ee, initialize_ee, print_json, redact_text


CORE_FIELDS = (
    "name",
    "id",
    "type",
    "startTime",
    "endTime",
    "createTime",
    "updateTime",
    "sizeBytes",
    "quota",
)

TABLE_TYPES = {"TABLE", "FEATURE_COLLECTION"}
IMAGE_TYPES = {"IMAGE"}

EXAMPLES = """examples:
  Inspect a user FeatureCollection Asset:
    python gee_asset_info.py --asset-id projects/YOUR_PROJECT/assets/research_area --project YOUR_PROJECT

  Inspect a public image:
    python gee_asset_info.py USGS/SRTMGL1_003 --project YOUR_PROJECT

  Inspect an ImageCollection or Folder:
    python gee_asset_info.py COPERNICUS/S2_SR_HARMONIZED --project YOUR_PROJECT
    python gee_asset_info.py projects/YOUR_PROJECT/assets --project YOUR_PROJECT

The output contains Asset metadata and bounded scalar/list probes only. It never
calls getInfo() on a complete Image, ImageCollection, or FeatureCollection.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "asset_id",
        nargs="?",
        help="Earth Engine Asset ID or resource name; may also use --asset-id.",
    )
    parser.add_argument("--asset-id", dest="named_asset_id", help="Earth Engine Asset ID.")
    parser.add_argument("--project", help="Google Cloud project used by ee.Initialize().")
    parser.add_argument(
        "--include-properties",
        action="store_true",
        help="Include a bounded subset of user-authored Asset properties.",
    )
    parser.add_argument(
        "--property-limit",
        type=int,
        default=100,
        help="Maximum property keys/values to return (1-500; default: 100).",
    )
    parser.add_argument(
        "--band-limit",
        type=int,
        default=200,
        help="Maximum band names/details to return (1-1000; default: 200).",
    )
    return parser


def resolve_asset_id(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.asset_id and args.named_asset_id and args.asset_id != args.named_asset_id:
        parser.error("the positional Asset ID and --asset-id disagree")
    asset_id = args.named_asset_id or args.asset_id
    if not asset_id:
        parser.error("an Asset ID is required")
    if not 1 <= args.property_limit <= 500:
        parser.error("--property-limit must be between 1 and 500")
    if not 1 <= args.band_limit <= 1000:
        parser.error("--band-limit must be between 1 and 1000")
    return asset_id


def lookup_failure_kind(exc: BaseException) -> str:
    message = redact_text(exc).lower()
    ambiguous_markers = (
        "does not exist or doesn't allow this operation",
        "does not exist or does not allow this operation",
        "not found or permission denied",
        "not found or inaccessible",
    )
    if any(marker in message for marker in ambiguous_markers):
        return "ambiguous"
    if any(
        marker in message
        for marker in ("not found", "does not exist", "no such asset", "http 404", "status 404")
    ):
        return "not_found"
    return "other"


def bounded_value(value: Any, depth: int = 0) -> Any:
    """Bound unusually large metadata values without altering the source Asset."""
    if depth >= 3:
        if isinstance(value, (dict, list, tuple)):
            return {"summary": "nested value omitted", "type": type(value).__name__}
        return value
    if isinstance(value, str):
        return value if len(value) <= 1000 else value[:1000] + "... [truncated]"
    if isinstance(value, dict):
        items = list(value.items())
        output = {
            str(key): bounded_value(item, depth + 1)
            for key, item in items[:50]
        }
        if len(items) > 50:
            output["_truncated_key_count"] = len(items) - 50
        return output
    if isinstance(value, (list, tuple)):
        output = [bounded_value(item, depth + 1) for item in value[:50]]
        if len(value) > 50:
            output.append({"_truncated_item_count": len(value) - 50})
        return output
    return value


def band_summary(bands: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(bands, list):
        return []
    output: list[dict[str, Any]] = []
    for band in bands[:limit]:
        if not isinstance(band, dict):
            continue
        output.append(
            {
                key: bounded_value(band.get(key))
                for key in ("id", "dataType", "grid", "pyramidingPolicy")
                if key in band
            }
        )
    return output


def metadata_geometry_summary(asset: dict[str, Any]) -> dict[str, Any] | None:
    geometry = asset.get("geometry")
    if not isinstance(geometry, dict):
        return None
    summary: dict[str, Any] = {
        "type": geometry.get("type"),
        "coordinates_omitted": "coordinates" in geometry,
    }
    if isinstance(geometry.get("bbox"), list) and len(geometry["bbox"]) <= 6:
        summary["bbox"] = geometry["bbox"]
    return summary


def grid_projection_from_bands(bands: Any) -> dict[str, Any] | None:
    if not isinstance(bands, list) or not bands or not isinstance(bands[0], dict):
        return None
    grid = bands[0].get("grid")
    if not isinstance(grid, dict):
        return None
    return {
        "band": bands[0].get("id"),
        "crs": grid.get("crsCode") or grid.get("crs"),
        "affine_transform": bounded_value(
            grid.get("affineTransform") or grid.get("transform")
        ),
        "dimensions": bounded_value(grid.get("dimensions")),
        "source": "asset_metadata",
    }


def probe_table(ee: Any, asset_id: str, result: dict[str, Any]) -> None:
    collection = ee.FeatureCollection(asset_id)
    count = int(collection.size().getInfo())
    result["feature_count"] = count
    result["empty"] = count == 0
    if count == 0:
        result["warnings"].append("FeatureCollection exists but contains no features.")
        return
    if result.get("geometry") is None:
        try:
            geometry_type = ee.Feature(collection.first()).geometry().type().getInfo()
            result["geometry"] = {
                "first_feature_type": geometry_type,
                "coordinates_omitted": True,
            }
        except Exception as exc:
            result["warnings"].append(
                f"Could not obtain first-feature geometry type: {type(exc).__name__}"
            )


def probe_image(
    ee: Any,
    asset_id: str,
    asset: dict[str, Any],
    result: dict[str, Any],
    band_limit: int,
) -> None:
    metadata_bands = asset.get("bands") if isinstance(asset.get("bands"), list) else []
    band_names = [
        band.get("id")
        for band in metadata_bands
        if isinstance(band, dict) and band.get("id") is not None
    ]
    band_count = len(metadata_bands)

    image = ee.Image(asset_id)
    if not metadata_bands:
        names = image.bandNames()
        band_data = ee.Dictionary(
            {"count": names.size(), "names": names.slice(0, band_limit)}
        ).getInfo()
        band_count = int(band_data.get("count") or 0)
        band_names = list(band_data.get("names") or [])

    result["band_count"] = band_count
    result["band_names"] = band_names[:band_limit]
    result["bands_truncated"] = band_count > band_limit
    result["bands"] = band_summary(metadata_bands, band_limit)

    if band_count == 0 or not band_names:
        result["obvious_errors"].append("Image exists but no bands were found.")
        return

    try:
        projection = image.select([band_names[0]]).projection()
        result["projection"] = projection.getInfo()
        nominal_scale = projection.nominalScale().getInfo()
        result["nominal_scale_m"] = (
            float(nominal_scale) if nominal_scale is not None else None
        )
        result["projection_band"] = band_names[0]
    except Exception as exc:
        fallback = grid_projection_from_bands(metadata_bands)
        if fallback is not None:
            result["projection"] = fallback
            result["warnings"].append(
                f"Used Asset grid metadata because live projection lookup failed: {type(exc).__name__}"
            )
        else:
            result["warnings"].append(
                f"Could not obtain first-band projection: {type(exc).__name__}"
            )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    asset_id = resolve_asset_id(args, parser)
    result: dict[str, Any] = {
        "status": "PENDING",
        "ok": False,
        "asset_id": asset_id,
        "requested_asset": asset_id,
        "asset_type": None,
        "exists": None,
        "project": args.project,
        "obvious_errors": [],
        "warnings": [],
    }

    try:
        ee = import_ee()
        project_selection = initialize_ee(ee, args.project)
        result["project_selection"] = project_selection
        result["project"] = (
            project_selection.get("effective_project")
            or project_selection.get("selected_project")
        )
        asset = ee.data.getAsset(asset_id)
        if not isinstance(asset, dict):
            raise FileNotFoundError(f"Earth Engine Asset not found: {asset_id}")
    except Exception as exc:
        details = error_payload("get_asset", exc)
        result.update(details)
        failure_kind = lookup_failure_kind(exc)
        if failure_kind == "not_found":
            result["status"] = "NOT_FOUND"
            result["exists"] = False
            result["obvious_errors"].append(f"Earth Engine Asset does not exist: {asset_id}")
            print_json(result)
            return 4
        if failure_kind == "ambiguous":
            result["status"] = "NOT_FOUND_OR_INACCESSIBLE"
            result["exists"] = None
            result["obvious_errors"].append(
                "Earth Engine reports that the Asset does not exist or is not accessible "
                f"to the current identity: {asset_id}"
            )
            result["possible_causes"] = [
                "Asset ID does not exist",
                "Current Earth Engine identity lacks permission",
            ]
            print_json(result)
            return 4
        result["status"] = "ERROR"
        result["obvious_errors"].append(details["message"])
        print_json(result)
        return 2

    asset_type = str(asset.get("type") or "UNKNOWN").upper()
    result["exists"] = True
    result["asset_type"] = asset_type
    result["asset_id"] = asset.get("name") or asset.get("id") or asset_id
    result["metadata"] = {key: asset.get(key) for key in CORE_FIELDS if key in asset}
    result["geometry"] = metadata_geometry_summary(asset)

    properties = asset.get("properties") if isinstance(asset.get("properties"), dict) else {}
    property_keys = sorted(str(key) for key in properties)
    result["property_count"] = len(property_keys)
    result["property_keys"] = property_keys[: args.property_limit]
    result["properties_truncated"] = len(property_keys) > args.property_limit
    if args.include_properties:
        result["properties"] = {
            key: bounded_value(properties[key])
            for key in property_keys[: args.property_limit]
        }

    try:
        if asset_type in TABLE_TYPES:
            probe_table(ee, asset_id, result)
        elif asset_type in IMAGE_TYPES:
            probe_image(ee, asset_id, asset, result, args.band_limit)
        else:
            metadata_bands = asset.get("bands")
            if isinstance(metadata_bands, list):
                result["band_count"] = len(metadata_bands)
                result["band_names"] = [
                    band.get("id")
                    for band in metadata_bands[: args.band_limit]
                    if isinstance(band, dict) and band.get("id") is not None
                ]
                result["bands_truncated"] = len(metadata_bands) > args.band_limit
                result["bands"] = band_summary(metadata_bands, args.band_limit)
                result["projection"] = grid_projection_from_bands(metadata_bands)
    except Exception as exc:
        details = error_payload("type_specific_probe", exc)
        result["obvious_errors"].append(details["message"])

    if result["obvious_errors"]:
        result["status"] = "PARTIAL"
        result["ok"] = False
        print_json(result)
        return 3
    result["status"] = "WARNING" if result["warnings"] else "OK"
    result["ok"] = True
    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
