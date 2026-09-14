#!/usr/bin/env python3
"""Optional geemap HTML rendering; failures never invalidate core GEE results.

Import save_interactive_map from executed research code. The caller initializes
Earth Engine and provides the real reference/result objects. No authentication,
Asset write, Export, or scientific unmask operation is performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
from importlib import metadata
from pathlib import Path
import os
import sys
from typing import Any, Callable
import webbrowser

from _gee_common import print_json, redact_text


def load_folium_backend() -> Any:
    """Load HTML backend without depending on a patched geemap installation.

    geemap's wildcard top-level import can shadow its basemaps module with a
    dictionary. Select Folium for a fresh import; if already loaded, temporarily
    resolve the real submodule. Restore all changed process state afterwards.
    No packages or third-party files are modified.
    """
    prior_backend = os.environ.get("USE_FOLIUM")
    package = sys.modules.get("geemap")
    restore_basemaps = package is not None and "geemap.foliumap" not in sys.modules
    had_basemaps = package is not None and hasattr(package, "basemaps")
    prior_basemaps = getattr(package, "basemaps", None)
    namespace_modified = False
    os.environ["USE_FOLIUM"] = "1"
    try:
        if restore_basemaps:
            package.basemaps = importlib.import_module("geemap.basemaps")
            namespace_modified = True
        return importlib.import_module("geemap.foliumap")
    finally:
        if prior_backend is None:
            os.environ.pop("USE_FOLIUM", None)
        else:
            os.environ["USE_FOLIUM"] = prior_backend
        if namespace_modified:
            if had_basemaps:
                package.basemaps = prior_basemaps
            else:
                delattr(package, "basemaps")


def preview_environment_info() -> dict:
    """Read the actual runtime identity without credentials or package mutation."""
    prefix = Path(sys.prefix)
    kind = "conda" if (prefix / "conda-meta").is_dir() else (
        "venv" if sys.prefix != sys.base_prefix else "system/base"
    )
    try:
        geemap_version = metadata.version("geemap")
    except metadata.PackageNotFoundError:
        geemap_version = None
    return {"environment_name": prefix.name, "environment_type": kind,
            "python_executable": sys.executable, "environment_prefix": sys.prefix,
            "python_version": sys.version.split()[0], "geemap_version": geemap_version,
            "proposed_install_command": [sys.executable, "-m", "pip", "install", "geemap"],
            "installation_performed": False}


def _static_fallback(roi: Any, image: Any, vis: dict, output: Path) -> dict:
    from gee_preview import save_image_preview
    return save_image_preview(
        image, region=roi.geometry(), output_path=output.with_name("result.png"),
        bands=vis["bands"], min_value=vis["min"], max_value=vis["max"],
        palette=vis.get("palette"), gamma=vis.get("gamma"), dimensions=1024,
    )


def save_interactive_map(
    *, roi: Any, reference_image: Any, result_image: Any,
    reference_vis: dict, result_vis: dict,
    output_path: str | Path = "preview/map.html",
    coverage_image: Any = None, coverage_vis: dict | None = None,
    result_name: str = "Research result", reference_name: str = "Reference imagery",
    class_values: list | None = None, class_legend: dict[str, str] | None = None,
    basemap: str = "OpenStreetMap", zoom: int = 8,
    open_browser: bool = True, static_fallback: Callable[[], dict] | None = None,
    allow_static_fallback: bool = False,
    map_factory: Callable[..., Any] | None = None,
) -> dict:
    """Save a map; missing geemap requires explicit user installation permission.

    map_factory is an offline test seam. Normal use lazily loads the geemap
    folium backend with ee_initialize=False to preserve the chosen identity and
    Project. class_values/class_legend remap only the display copy, not results.
    """
    output = Path(output_path)
    warnings: list[str] = []
    record: dict = {"map_generated": False, "output_path": None, "warnings": warnings}
    if output.exists():
        record["state"] = "MAP_CONFLICT"
        warnings.append("Map already exists; choose a new artifact version. Nothing was overwritten.")
        return record
    try:
        if output.suffix.lower() != ".html":
            raise ValueError("Map output must end in .html")
        if any(item is None for item in (roi, reference_image, result_image)):
            raise ValueError("Real ROI, reference image, and result image are required")
        if map_factory is None:
            try:
                map_factory = load_folium_backend().Map
            except ImportError as exc:
                record.update(state="GEEMAP_INSTALL_CONFIRMATION_REQUIRED",
                              environment=preview_environment_info(),
                              dependency_error=redact_text(exc),
                              action_required="Show this environment and ask user permission to install geemap here.")
                warnings.append("Await explicit user consent. No installation, environment change, or static fallback was performed.")
                return record
        output.parent.mkdir(parents=True, exist_ok=True)

        m = map_factory(ee_initialize=False, basemap=basemap, zoom=zoom)
        m.centerObject(roi, zoom=zoom)
        m.addLayer(reference_image, dict(reference_vis), reference_name, False)
        display_image = result_image
        display_vis = dict(result_vis)
        if class_legend is not None:
            if not class_values or len(class_values) != len(class_legend):
                raise ValueError("class_values and class_legend must have matching nonzero lengths")
            if len(set(class_values)) != len(class_values):
                raise ValueError("class_values must be unique")
            display_image = result_image.remap(class_values, list(range(len(class_values))))
            display_vis = {"min": 0, "max": max(1, len(class_values) - 1),
                           "palette": list(class_legend.values())}
        m.addLayer(display_image, display_vis, result_name, True)
        if coverage_image is not None:
            if coverage_vis is None:
                raise ValueError("coverage_vis is required when coverage_image is supplied")
            m.addLayer(coverage_image, dict(coverage_vis), "Coverage / Mask", False)
        else:
            warnings.append("Coverage / Mask not supplied; report applicability in the research record.")
        boundary = roi.style(color="ff0000", fillColor="00000000", width=2)
        m.addLayer(boundary, {}, "ROI boundary", True)
        if class_legend is not None:
            m.add_legend(title=result_name, legend_dict=dict(class_legend), draggable=False)
        else:
            if not all(key in display_vis for key in ("palette", "min", "max")):
                raise ValueError("Continuous result requires explicit palette, min, and max")
            m.add_colorbar(display_vis, label=result_name)
        m.add_layer_control()
        html = m.get_root().render()
        # Never persist OAuth material even if a rendering backend leaks it.
        if "ya29." in html or "-----BEGIN PRIVATE KEY-----" in html:
            raise ValueError("Rendering output contained credential-like material; HTML was not saved")
        with output.open("x", encoding="utf-8") as handle:
            handle.write(html)
        record.update(state="MAP_GENERATED", map_generated=True,
                      output_path=str(output.resolve()),
                      sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                      visualization={"reference": reference_vis, "result": display_vis,
                                     "class_values": class_values, "class_legend": class_legend,
                                     "coverage": coverage_vis})
        warnings.append("Online tiles may expire; rerun code to refresh. HTML is not offline research data.")
        if open_browser:
            try:
                record["browser_open_requested"] = webbrowser.open(output.resolve().as_uri())
                if not record["browser_open_requested"]:
                    warnings.append("Browser did not accept the open request; open the saved HTML manually.")
            except Exception as exc:
                warnings.append("Browser open failed: " + redact_text(exc))
        return record
    except Exception as exc:
        record.setdefault("state", "MAP_FAILED")
        record["environment"] = preview_environment_info()
        warnings.append("Map stage failed (core research result remains valid): " + redact_text(exc))
        if not allow_static_fallback:
            warnings.append("Offer static preview to the user; explicit acceptance is required before fallback.")
            return record
        try:
            record["static_preview"] = (
                static_fallback() if static_fallback is not None
                else _static_fallback(roi, result_image, result_vis, output)
            )
        except Exception as fallback_exc:
            warnings.append("Static fallback failed: " + redact_text(fallback_exc))
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Import save_interactive_map into research code; CLI never computes or exports.")
    parser.add_argument("--show-contract", action="store_true")
    parser.add_argument("--environment", action="store_true", help="Read actual Python environment; never installs packages.")
    args = parser.parse_args()
    if args.environment:
        print_json(preview_environment_info())
    elif args.show_contract:
        print_json({"backend": "geemap.foliumap + Earth Engine Python API",
                    "default_path": "preview/map.html", "all_modes": ["A", "B", "C", "D", "E"],
                    "missing_geemap": "ask user installation permission with actual environment details",
                    "automatic_install": False, "static_fallback_requires_acceptance": True,
                    "overwrite": False, "exports": False})
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
