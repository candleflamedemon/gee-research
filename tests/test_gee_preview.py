"""Offline tests for gee_preview; no Earth Engine request or export is sent."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gee_preview import (  # noqa: E402
    PreviewConflictError,
    PreviewValidationError,
    save_image_preview,
)


PNG_DATA = b"\x89PNG\r\n\x1a\n" + b"offline-preview"


class FakeImage:
    def __init__(self) -> None:
        self.params = None

    def getThumbURL(self, params):
        self.params = params
        return "https://example.invalid/thumb?signature=SENSITIVE_VALUE"


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        return self.payload


def fake_opener(_request, *, timeout):
    if timeout <= 0:
        raise AssertionError("timeout must be positive")
    return FakeResponse(PNG_DATA)


class PreviewTests(unittest.TestCase):
    def test_single_band_preview_is_bounded_and_url_is_not_returned(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ndvi.png"
            image = FakeImage()
            region = object()
            result = save_image_preview(
                image,
                region=region,
                output_path=output,
                bands=["NDVI"],
                min_value=-0.2,
                max_value=0.8,
                palette=["#440154", "#fde725"],
                dimensions="800x600",
                url_opener=fake_opener,
            )
            self.assertEqual(output.read_bytes(), PNG_DATA)
            self.assertIs(image.params["region"], region)
            self.assertEqual(image.params["dimensions"], "800x600")
            self.assertFalse(result["scientific_pixels_modified"])
            self.assertFalse(result["export_task_created"])
            self.assertNotIn("SENSITIVE_VALUE", repr(result))

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "existing.png"
            output.write_bytes(b"original")
            with self.assertRaises(PreviewConflictError):
                save_image_preview(
                    FakeImage(),
                    region=object(),
                    output_path=output,
                    bands="NDVI",
                    min_value=-1,
                    max_value=1,
                    url_opener=fake_opener,
                )
            self.assertEqual(output.read_bytes(), b"original")

    def test_palette_is_rejected_for_rgb(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(PreviewValidationError, "single-band"):
                save_image_preview(
                    FakeImage(),
                    region=object(),
                    output_path=Path(temp_dir) / "rgb.png",
                    bands=["B4", "B3", "B2"],
                    min_value=0,
                    max_value=0.3,
                    palette=["black", "white"],
                    url_opener=fake_opener,
                )

    def test_oversized_dimensions_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(PreviewValidationError, "4096"):
                save_image_preview(
                    FakeImage(),
                    region=object(),
                    output_path=Path(temp_dir) / "large.png",
                    bands="NDVI",
                    min_value=-1,
                    max_value=1,
                    dimensions="5000x100",
                    url_opener=fake_opener,
                )


if __name__ == "__main__":
    unittest.main()
