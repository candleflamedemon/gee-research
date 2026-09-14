#!/usr/bin/env python3
"""Create bounded local previews for Earth Engine Images without exporting.

The reusable ``save_image_preview`` function accepts any computed ``ee.Image``.
The CLI is intentionally narrower and previews an existing Image Asset. It
requires an explicit region and visualization range, never calls ``unmask``,
never creates an Asset or batch task, and never reports the signed thumbnail
URL returned by Earth Engine.
"""

from __future__ import annotations

import argparse
import hashlib
import numbers
import re
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence

from _gee_common import error_payload, import_ee, initialize_ee, print_json


MAX_EDGE_PIXELS = 4096
MAX_TOTAL_PIXELS = 16_777_216
DEFAULT_MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024


class PreviewValidationError(ValueError):
    """Preview parameters are missing, unsafe, or internally inconsistent."""


class PreviewConflictError(FileExistsError):
    """The local preview path already exists and will not be overwritten."""


class PreviewDownloadError(RuntimeError):
    """Earth Engine did not return a valid bounded preview image."""


def _normalize_dimensions(value: int | str) -> int | str:
    if isinstance(value, bool):
        raise PreviewValidationError("dimensions must be a positive integer or WIDTHxHEIGHT")
    if isinstance(value, int):
        width = height = value
        normalized: int | str = value
    elif isinstance(value, str) and re.fullmatch(r"[1-9]\d*", value.strip()):
        width = height = int(value)
        normalized = width
    elif isinstance(value, str) and re.fullmatch(r"[1-9]\d*[xX][1-9]\d*", value.strip()):
        width_text, height_text = re.split(r"[xX]", value.strip())
        width, height = int(width_text), int(height_text)
        normalized = f"{width}x{height}"
    else:
        raise PreviewValidationError("dimensions must be a positive integer or WIDTHxHEIGHT")
    if width > MAX_EDGE_PIXELS or height > MAX_EDGE_PIXELS:
        raise PreviewValidationError(f"each preview edge must be <= {MAX_EDGE_PIXELS} pixels")
    if width * height > MAX_TOTAL_PIXELS:
        raise PreviewValidationError(
            f"preview pixel count must be <= {MAX_TOTAL_PIXELS}"
        )
    return normalized


def _normalize_bands(value: str | Sequence[str]) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value)
    bands = [str(item).strip() for item in items if str(item).strip()]
    if len(bands) not in {1, 3}:
        raise PreviewValidationError("bands must contain exactly one band or three RGB bands")
    return bands


def _normalize_palette(value: str | Sequence[str] | None) -> list[str] | None:
    if value is None:
        return None
    items = value.split(",") if isinstance(value, str) else list(value)
    palette = [str(item).strip() for item in items if str(item).strip()]
    if not palette:
        raise PreviewValidationError("palette must contain at least one color")
    return palette


def _normalize_numeric(value: Any, label: str) -> float | list[float]:
    if isinstance(value, bool):
        raise PreviewValidationError(f"{label} must be numeric")
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, (list, tuple)) and value:
        if any(isinstance(item, bool) or not isinstance(item, numbers.Real) for item in value):
            raise PreviewValidationError(f"{label} must contain only numbers")
        return [float(item) for item in value]
    raise PreviewValidationError(f"{label} must be a number or a non-empty numeric sequence")


def _normalize_range(min_value: Any, max_value: Any) -> tuple[Any, Any]:
    minimum = _normalize_numeric(min_value, "min_value")
    maximum = _normalize_numeric(max_value, "max_value")
    if isinstance(minimum, list) != isinstance(maximum, list):
        raise PreviewValidationError("min_value and max_value must use matching shapes")
    if isinstance(minimum, list):
        if len(minimum) != len(maximum):
            raise PreviewValidationError("min_value and max_value sequences must have equal length")
        pairs = zip(minimum, maximum)
    else:
        pairs = [(minimum, maximum)]
    if any(low >= high for low, high in pairs):
        raise PreviewValidationError("every min_value must be smaller than max_value")
    return minimum, maximum


def _normalize_format(value: str | None, output_path: Path) -> str:
    suffix = output_path.suffix.lower()
    inferred = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}.get(suffix)
    requested = value.lower() if value else inferred
    if requested == "jpeg":
        requested = "jpg"
    if requested not in {"png", "jpg"}:
        raise PreviewValidationError("format must be png or jpg, or output must use that suffix")
    valid_suffixes = {"png": {".png"}, "jpg": {".jpg", ".jpeg"}}
    if suffix not in valid_suffixes[requested]:
        raise PreviewValidationError("output suffix does not match the requested image format")
    return requested


def _validate_signature(data: bytes, image_format: str) -> None:
    valid = data.startswith(b"\x89PNG\r\n\x1a\n") if image_format == "png" else data.startswith(b"\xff\xd8")
    if not valid:
        raise PreviewDownloadError(f"response is not a valid {image_format} image")


def save_image_preview(
    image: Any,
    *,
    region: Any,
    output_path: str | Path,
    bands: str | Sequence[str],
    min_value: Any,
    max_value: Any,
    palette: str | Sequence[str] | None = None,
    gamma: float | None = None,
    dimensions: int | str = 1024,
    image_format: str | None = None,
    timeout_seconds: float = 120,
    max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    url_opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Download an Earth Engine thumbnail to a new local file.

    ``region`` and visualization limits are mandatory so a caller cannot
    accidentally request an unbounded or scientifically ambiguous preview.
    The returned metadata deliberately excludes Earth Engine's signed URL.
    """
    if image is None or not callable(getattr(image, "getThumbURL", None)):
        raise PreviewValidationError("image must provide Earth Engine getThumbURL(params)")
    if region is None:
        raise PreviewValidationError("region is required; whole-image previews are disabled")
    if timeout_seconds <= 0 or max_download_bytes <= 0:
        raise PreviewValidationError("timeout_seconds and max_download_bytes must be positive")

    output = Path(output_path)
    if not output.name:
        raise PreviewValidationError("output_path must name a file")
    if output.exists():
        raise PreviewConflictError(f"preview already exists and will not be overwritten: {output}")
    if not output.parent.is_dir():
        raise PreviewValidationError(
            "preview parent directory must already exist; create it through the artifact workflow"
        )

    normalized_bands = _normalize_bands(bands)
    normalized_palette = _normalize_palette(palette)
    if normalized_palette is not None and len(normalized_bands) != 1:
        raise PreviewValidationError("palette is supported only for a single-band preview")
    minimum, maximum = _normalize_range(min_value, max_value)
    normalized_dimensions = _normalize_dimensions(dimensions)
    normalized_format = _normalize_format(image_format, output)
    if gamma is not None and (isinstance(gamma, bool) or gamma <= 0):
        raise PreviewValidationError("gamma must be positive")

    params: dict[str, Any] = {
        "region": region,
        "bands": normalized_bands,
        "min": minimum,
        "max": maximum,
        "dimensions": normalized_dimensions,
        "format": normalized_format,
    }
    if normalized_palette is not None:
        params["palette"] = normalized_palette
    if gamma is not None:
        params["gamma"] = float(gamma)

    signed_url = image.getThumbURL(params)
    opener = url_opener or urllib.request.urlopen
    request = urllib.request.Request(
        signed_url,
        headers={"User-Agent": "gee-research-preview/1.0"},
    )
    with opener(request, timeout=timeout_seconds) as response:
        data = response.read(max_download_bytes + 1)
    if len(data) > max_download_bytes:
        raise PreviewDownloadError(
            f"preview exceeds the {max_download_bytes}-byte safety limit"
        )
    _validate_signature(data, normalized_format)

    try:
        with output.open("xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise PreviewConflictError(
            f"preview appeared during download and will not be overwritten: {output}"
        ) from exc

    return {
        "output_path": str(output.resolve()),
        "format": normalized_format,
        "dimensions": normalized_dimensions,
        "bands": normalized_bands,
        "min": minimum,
        "max": maximum,
        "palette": normalized_palette,
        "gamma": gamma,
        "region_supplied": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "scientific_pixels_modified": False,
        "export_task_created": False,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download a bounded PNG/JPEG preview of an existing Earth Engine Image "
            "Asset. For computed images, import save_image_preview instead."
        ),
        epilog=(
            "Example: python gee_preview.py --image-asset projects/p/assets/result "
            "--roi projects/p/assets/roi --project p --output preview.png "
            "--bands NDVI --min -0.2 --max 0.8 --palette '#440154,#21918c,#fde725'"
        ),
    )
    parser.add_argument("--image-asset", required=True, help="Existing Earth Engine Image Asset ID.")
    parser.add_argument("--roi", required=True, help="FeatureCollection/Table or Image Asset used as region.")
    parser.add_argument("--output", required=True, help="New .png, .jpg, or .jpeg output path.")
    parser.add_argument("--project", help="Computation Project; project-selection rules apply if omitted.")
    parser.add_argument("--bands", required=True, help="One band, or three comma-separated RGB bands.")
    parser.add_argument("--min", dest="min_value", required=True, type=float, help="Visualization minimum.")
    parser.add_argument("--max", dest="max_value", required=True, type=float, help="Visualization maximum.")
    parser.add_argument("--palette", help="Comma-separated colors for a single-band preview.")
    parser.add_argument("--gamma", type=float, help="Optional positive display gamma.")
    parser.add_argument("--dimensions", default="1024", help="Maximum edge or WIDTHxHEIGHT, capped at 4096.")
    parser.add_argument("--format", choices=("png", "jpg", "jpeg"), help="Usually inferred from output suffix.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        ee = import_ee()
        project = initialize_ee(ee, project=args.project)

        image_asset = ee.data.getAsset(args.image_asset)
        image_type = image_asset.get("type") if isinstance(image_asset, dict) else None
        if image_type != "IMAGE":
            raise PreviewValidationError(
                f"--image-asset must be an IMAGE; observed type={image_type!r}"
            )

        roi_asset = ee.data.getAsset(args.roi)
        roi_type = roi_asset.get("type") if isinstance(roi_asset, dict) else None
        if roi_type == "TABLE":
            region = ee.FeatureCollection(args.roi).geometry()
        elif roi_type == "IMAGE":
            region = ee.Image(args.roi).geometry()
        else:
            raise PreviewValidationError(
                f"--roi must be a TABLE/FeatureCollection or IMAGE; observed type={roi_type!r}"
            )

        result = save_image_preview(
            ee.Image(args.image_asset),
            region=region,
            output_path=args.output,
            bands=args.bands,
            min_value=args.min_value,
            max_value=args.max_value,
            palette=args.palette,
            gamma=args.gamma,
            dimensions=args.dimensions,
            image_format=args.format,
        )
        print_json(
            {
                "ok": True,
                "project": project,
                "image_asset": args.image_asset,
                "roi_asset": args.roi,
                "preview": result,
            }
        )
        return 0
    except Exception as exc:
        print_json(error_payload("preview", exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "PreviewConflictError",
    "PreviewDownloadError",
    "PreviewValidationError",
    "save_image_preview",
]
