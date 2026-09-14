#!/usr/bin/env python3
"""Inspect a filtered Earth Engine ImageCollection with bounded metadata requests."""

from __future__ import annotations

import argparse
from typing import Any

from _gee_common import error_payload, import_ee, initialize_ee, iso_from_millis, print_json


EXAMPLES = """examples:
  Probe Sentinel-2 over an ROI Asset (end date is exclusive):
    python gee_collection_probe.py --dataset COPERNICUS/S2_SR_HARMONIZED --start-date 2024-01-01 --end-date 2024-02-01 --roi projects/YOUR_PROJECT/assets/research_area --project YOUR_PROJECT

  Probe Landsat over a bounding box:
    python gee_collection_probe.py --dataset LANDSAT/LC09/C02/T1_L2 --start-date 2024-06-01 --end-date 2024-07-01 --bbox 116.2 39.7 116.6 40.1 --project YOUR_PROJECT

  Legacy positional dataset syntax remains supported:
    python gee_collection_probe.py MODIS/061/MOD13Q1 --start 2024-01-01 --end 2024-03-01 --point 116.4 39.9

The script retrieves only scalar or small metadata summaries. It never downloads
an ROI FeatureCollection or a complete Image/ImageCollection with getInfo().
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "collection_id",
        nargs="?",
        help="Legacy positional ImageCollection ID; prefer --dataset.",
    )
    parser.add_argument("--dataset", help="Earth Engine ImageCollection dataset/Asset ID.")
    parser.add_argument(
        "--start-date",
        "--start",
        dest="start_date",
        help="Inclusive start date, for example 2024-01-01.",
    )
    parser.add_argument(
        "--end-date",
        "--end",
        dest="end_date",
        help="Exclusive end date, for example 2024-02-01.",
    )
    parser.add_argument(
        "--roi",
        help="Earth Engine TABLE/FeatureCollection Asset ID used for filterBounds().",
    )
    spatial = parser.add_mutually_exclusive_group()
    spatial.add_argument(
        "--point",
        nargs=2,
        type=float,
        metavar=("LON", "LAT"),
        help="Point ROI alternative to --roi.",
    )
    spatial.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("W", "S", "E", "N"),
        help="Bounding-box ROI alternative to --roi.",
    )
    parser.add_argument(
        "--sample-point",
        nargs=2,
        type=float,
        metavar=("LON", "LAT"),
        help="Optionally sample the first image at one point.",
    )
    parser.add_argument("--scale", type=float, help="Scale in meters for --sample-point.")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of sample image IDs to return (1-50; default: 5).",
    )
    parser.add_argument(
        "--band-limit",
        type=int,
        default=200,
        help="Maximum first-image band names to return (1-1000; default: 200).",
    )
    parser.add_argument("--project", help="Google Cloud project used by ee.Initialize().")
    return parser


def resolve_dataset(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.dataset and args.collection_id and args.dataset != args.collection_id:
        parser.error("--dataset and the legacy positional dataset disagree")
    dataset = args.dataset or args.collection_id
    if not dataset:
        parser.error("--dataset is required (or use the legacy positional dataset)")
    return dataset


def validate_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date and --end-date must be supplied together")
    if args.roi and (args.point or args.bbox):
        parser.error("use only one of --roi, --point, or --bbox")
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    if not 1 <= args.band_limit <= 1000:
        parser.error("--band-limit must be between 1 and 1000")
    if args.scale is not None and args.scale <= 0:
        parser.error("--scale must be positive")


def apply_spatial_filter(
    ee: Any, collection: Any, args: argparse.Namespace
) -> tuple[Any, dict[str, Any] | None]:
    if args.roi:
        asset = ee.data.getAsset(args.roi)
        asset_type = str(asset.get("type", "UNKNOWN")).upper()
        if asset_type not in {"TABLE", "FEATURE_COLLECTION"}:
            raise ValueError(
                f"--roi must identify a TABLE/FeatureCollection Asset; got {asset_type}"
            )
        # Passing the server-side FeatureCollection avoids downloading its features or
        # geometry. A large/complex ROI can still make the server-side filter expensive.
        roi = ee.FeatureCollection(args.roi)
        return collection.filterBounds(roi), {
            "kind": "asset",
            "asset_id": args.roi,
            "asset_type": asset_type,
        }
    if args.point:
        point = [float(args.point[0]), float(args.point[1])]
        return collection.filterBounds(ee.Geometry.Point(point)), {
            "kind": "point",
            "coordinates": point,
        }
    if args.bbox:
        bbox = [float(value) for value in args.bbox]
        return collection.filterBounds(ee.Geometry.Rectangle(bbox)), {
            "kind": "bbox",
            "coordinates": bbox,
        }
    return collection, None


def base_result(dataset: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "status": "PENDING",
        "ok": False,
        "dataset_id": dataset,
        "collection_id": dataset,
        "project": args.project,
        "time_range": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "end_is_exclusive": True if args.end_date else None,
        },
        "image_count": None,
        "count": None,
        "empty": None,
        "obvious_errors": [],
        "warnings": [],
    }


def projection_summary(first: Any, band_name: str) -> tuple[dict[str, Any] | None, float | None]:
    projection = first.select([band_name]).projection()
    projection_info = projection.getInfo()
    nominal_scale = projection.nominalScale().getInfo()
    return projection_info, float(nominal_scale) if nominal_scale is not None else None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dataset = resolve_dataset(args, parser)
    validate_args(args, parser)
    result = base_result(dataset, args)
    if not args.start_date:
        result["warnings"].append(
            "No date filter was supplied; counting a large collection can be slow."
        )
    if not (args.roi or args.point or args.bbox):
        result["warnings"].append(
            "No spatial filter was supplied; image_count describes the full temporal collection."
        )

    try:
        ee = import_ee()
        project_selection = initialize_ee(ee, args.project)
        result["project_selection"] = project_selection
        result["project"] = (
            project_selection.get("effective_project")
            or project_selection.get("selected_project")
        )

        collection = ee.ImageCollection(dataset)
        if args.start_date:
            collection = collection.filterDate(args.start_date, args.end_date)
        collection, roi_summary = apply_spatial_filter(ee, collection, args)
        result["roi"] = roi_summary

        # size().getInfo() retrieves one integer. Apply date and ROI filters first so
        # the server does not count a broader collection than the user requested.
        count = int(collection.size().getInfo())
        result["image_count"] = count
        result["count"] = count
        result["empty"] = count == 0

        if count == 0:
            result["status"] = "EMPTY"
            result["obvious_errors"].append(
                "ImageCollection is empty after the requested filters; do not call "
                "first(), median(), mean(), mosaic(), qualityMosaic(), or toBands()."
            )
            print_json(result)
            return 4

        limited = collection.limit(args.limit)
        first = ee.Image(limited.first())

        # Each getInfo() below is bounded: band/property-name lists, a few scalar
        # properties, and at most --limit image IDs. No raster or ROI features are
        # materialized on the client.
        band_names_object = first.bandNames()
        property_names_object = first.propertyNames()
        first_metadata = ee.Dictionary(
            {
                "id": first.get("system:id"),
                "time_start_ms": first.get("system:time_start"),
                "band_count": band_names_object.size(),
                "band_names": band_names_object.slice(0, args.band_limit),
                "property_count": property_names_object.size(),
                "property_names": property_names_object.slice(0, 100),
                "sample_image_ids": limited.aggregate_array("system:id"),
            }
        ).getInfo()
        band_count = int(first_metadata.get("band_count") or 0)
        band_names = list(first_metadata.get("band_names") or [])
        property_count = int(first_metadata.get("property_count") or 0)
        property_names = sorted(first_metadata.get("property_names") or [])
        time_start = first_metadata.get("time_start_ms")

        result["sample_image_ids"] = first_metadata.get("sample_image_ids") or []
        result["first_image"] = {
            "id": first_metadata.get("id"),
            "date_ms": time_start,
            "date_utc": iso_from_millis(time_start),
            "time_start_ms": time_start,
            "time_start_utc": iso_from_millis(time_start),
            "band_count": band_count,
            "bands": band_names,
            "bands_truncated": band_count > len(band_names),
            "property_count": property_count,
            "property_names": property_names,
            "properties_truncated": property_count > len(property_names),
            "nominal_scale_m": None,
            "projection": None,
            "first_band_projection": None,
        }

        if band_count == 0 or not band_names:
            result["status"] = "ERROR"
            result["obvious_errors"].append(
                "The collection is non-empty, but its first image has no bands."
            )
            print_json(result)
            return 5

        try:
            projection, nominal_scale = projection_summary(first, band_names[0])
            result["first_image"]["projection"] = projection
            result["first_image"]["first_band_projection"] = projection
            result["first_image"]["nominal_scale_m"] = nominal_scale
        except Exception as exc:
            result["warnings"].append(
                f"Could not obtain first-band projection/nominal scale: {type(exc).__name__}"
            )

        if result["first_image"]["date_utc"] is None:
            result["obvious_errors"].append(
                "The first image has no usable system:time_start date."
            )

        if args.sample_point:
            region = ee.Geometry.Point(args.sample_point)
            parameters: dict[str, Any] = {
                "reducer": ee.Reducer.first(),
                "geometry": region,
                "bestEffort": True,
                "maxPixels": 1_000_000,
            }
            if args.scale:
                parameters["scale"] = args.scale
            result["first_image_point_sample"] = first.reduceRegion(**parameters).getInfo()
            result["sample_point"] = args.sample_point
            result["sample_scale"] = args.scale

        result["status"] = "WARNING" if result["obvious_errors"] or result["warnings"] else "OK"
        result["ok"] = True
    except Exception as exc:
        details = error_payload("collection_probe", exc)
        result.update(details)
        result["status"] = "ERROR"
        result["obvious_errors"].append(details["message"])
        print_json(result)
        return 2

    print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
