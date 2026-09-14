"""Offline tests for gee_export_helpers; no Earth Engine task is submitted."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gee_export_helpers import (  # noqa: E402
    AssetConflictError,
    AssetTargetCheckError,
    ExportValidationError,
    create_image_to_asset_task,
    create_image_to_drive_task,
    create_table_to_asset_task,
    create_table_to_drive_task,
    start_prepared_task,
)


class FakeTask:
    def __init__(self) -> None:
        self.id = None
        self.start_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self.id = "TASK_TEST_001"

    def status(self):
        return {
            "id": self.id,
            "state": "READY" if self.start_calls else "UNSUBMITTED",
            "description": "offline_test",
        }


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def factory(self, name: str):
        def make(**kwargs):
            self.calls.append((name, kwargs))
            return FakeTask()

        return make


def fake_ee(asset_lookup):
    recorder = Recorder()
    image = SimpleNamespace(
        toAsset=recorder.factory("image.toAsset"),
        toDrive=recorder.factory("image.toDrive"),
    )
    table = SimpleNamespace(
        toAsset=recorder.factory("table.toAsset"),
        toDrive=recorder.factory("table.toDrive"),
    )
    ee = SimpleNamespace(
        data=SimpleNamespace(getAsset=asset_lookup),
        batch=SimpleNamespace(Export=SimpleNamespace(image=image, table=table)),
    )
    return ee, recorder


class ExportHelpersTests(unittest.TestCase):
    def test_drive_builders_forward_names_without_fixed_science_defaults(self):
        ee, recorder = fake_ee(lambda _asset_id: None)
        image_export = create_image_to_drive_task(
            object(),
            description="image_test",
            folder="research_folder",
            file_name_prefix="ndvi_2024",
            region="ROI",
            scale=10,
            crs="EPSG:32649",
            max_pixels=123456,
            ee_module=ee,
        )
        table_export = create_table_to_drive_task(
            object(),
            description="table_test",
            folder="research_folder",
            file_name_prefix="stats_2024",
            selectors=["class", "area"],
            ee_module=ee,
        )
        self.assertEqual(image_export.task.start_calls, 0)
        self.assertEqual(table_export.task.start_calls, 0)
        image_kwargs = recorder.calls[0][1]
        table_kwargs = recorder.calls[1][1]
        self.assertEqual(image_kwargs["folder"], "research_folder")
        self.assertEqual(image_kwargs["fileNamePrefix"], "ndvi_2024")
        self.assertEqual(image_kwargs["scale"], 10)
        self.assertNotIn("dimensions", image_kwargs)
        self.assertNotIn("crsTransform", image_kwargs)
        self.assertEqual(table_kwargs["fileNamePrefix"], "stats_2024")

    def test_asset_conflict_blocks_task_creation(self):
        ee, recorder = fake_ee(lambda asset_id: {"name": asset_id, "type": "IMAGE"})
        with self.assertRaisesRegex(AssetConflictError, "already exists"):
            create_image_to_asset_task(
                object(),
                description="conflict_test",
                asset_id="projects/p/assets/existing",
                ee_module=ee,
            )
        self.assertEqual(recorder.calls, [])

    def test_ambiguous_asset_lookup_is_blocked_by_default(self):
        def ambiguous(_asset_id):
            raise RuntimeError("Asset does not exist or doesn't allow this operation")

        ee, recorder = fake_ee(ambiguous)
        with self.assertRaises(AssetTargetCheckError):
            create_table_to_asset_task(
                object(),
                description="ambiguous_test",
                asset_id="projects/p/assets/unknown",
                ee_module=ee,
            )
        self.assertEqual(recorder.calls, [])

    def test_unverified_opt_in_still_disables_overwrite(self):
        def ambiguous(_asset_id):
            raise RuntimeError("Asset does not exist or doesn't allow this operation")

        ee, recorder = fake_ee(ambiguous)
        prepared = create_table_to_asset_task(
            object(),
            description="new_table",
            asset_id="projects/p/assets/new_table",
            allow_unverified_target=True,
            ee_module=ee,
        )
        self.assertFalse(recorder.calls[0][1]["overwrite"])
        self.assertIsNone(prepared.asset_preflight["exists"])

    def test_submission_gate_and_initial_status(self):
        ee, _recorder = fake_ee(lambda _asset_id: None)
        prepared = create_table_to_drive_task(
            object(), description="submit_test", ee_module=ee
        )
        dry_run = start_prepared_task(prepared)
        self.assertFalse(dry_run["submitted"])
        self.assertEqual(dry_run["initial_state"], "UNSUBMITTED")
        self.assertEqual(prepared.task.start_calls, 0)

        started = start_prepared_task(prepared, submit=True)
        self.assertTrue(started["submitted"])
        self.assertEqual(started["task_id"], "TASK_TEST_001")
        self.assertEqual(started["initial_state"], "READY")
        self.assertEqual(prepared.task.start_calls, 1)
        self.assertFalse(started["waited_for_completion"])

    def test_invalid_grid_combination_is_rejected(self):
        ee, recorder = fake_ee(lambda _asset_id: None)
        with self.assertRaisesRegex(ExportValidationError, "mutually exclusive"):
            create_image_to_drive_task(
                object(),
                description="bad_grid",
                scale=10,
                dimensions=1000,
                ee_module=ee,
            )
        self.assertEqual(recorder.calls, [])


if __name__ == "__main__":
    unittest.main()
