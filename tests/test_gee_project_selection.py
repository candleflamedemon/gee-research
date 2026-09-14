from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _gee_common import (
    ProjectConfigError,
    initialize_ee,
    json_safe,
    redact_text,
    resolve_project,
)


class _State:
    def __init__(self, project=None):
        self.cloud_api_user_project = project


class _Data:
    def __init__(self):
        self.project = None

    def _get_state(self):
        return _State(self.project)


class _EE:
    def __init__(self, default_project="default-project"):
        self.data = _Data()
        self.default_project = default_project
        self.calls = []

    def Initialize(self, **kwargs):
        self.calls.append(kwargs)
        self.data.project = kwargs.get("project", self.default_project)


class ProjectSelectionTests(unittest.TestCase):
    def write_config(self, root: Path, payload: dict) -> Path:
        path = root / ".gee-project.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_explicit_project_overrides_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_config(root, {"project": "config-project"})
            selection = resolve_project("user-project", cwd=root)
            self.assertEqual(selection.selected_project, "user-project")
            self.assertEqual(selection.selection_source, "explicit_argument")

    def test_current_workspace_config_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_config(root, {"project": "config-project"})
            selection = resolve_project(cwd=root)
            self.assertEqual(selection.selected_project, "config-project")
            self.assertEqual(selection.selection_source, "project_config")

    def test_missing_config_defers_to_earth_engine_default(self):
        with tempfile.TemporaryDirectory() as directory:
            selection = resolve_project(cwd=directory)
            self.assertIsNone(selection.selected_project)
            self.assertEqual(selection.selection_source, "earth_engine_default")

    def test_parent_directory_is_not_searched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "child"
            child.mkdir()
            self.write_config(root, {"project": "unrelated-parent-project"})
            selection = resolve_project(cwd=child)
            self.assertIsNone(selection.selected_project)
            self.assertEqual(selection.selection_source, "earth_engine_default")

    def test_credential_like_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_config(
                root,
                {"project": "config-project", "refresh_token": "do-not-store-this"},
            )
            with self.assertRaises(ProjectConfigError):
                resolve_project(cwd=root)

    def test_initializer_uses_config_and_reports_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_config(root, {"project": "config-project"})
            ee = _EE()
            result = initialize_ee(ee, cwd=root)
            self.assertEqual(ee.calls, [{"project": "config-project"}])
            self.assertEqual(result["effective_project"], "config-project")
            self.assertEqual(result["selection_source"], "project_config")

    def test_initializer_uses_earth_engine_default_without_config(self):
        with tempfile.TemporaryDirectory() as directory:
            ee = _EE(default_project="current-default")
            result = initialize_ee(ee, cwd=directory)
            self.assertEqual(ee.calls, [{}])
            self.assertEqual(result["effective_project"], "current-default")
            self.assertEqual(result["selection_source"], "earth_engine_default")

    def test_sensitive_output_values_are_redacted(self):
        safe = json_safe(
            {
                "refresh_token": "synthetic-secret-value",
                "credential_files_opened_by_script": False,
            }
        )
        self.assertEqual(safe["refresh_token"], "[REDACTED]")
        self.assertFalse(safe["credential_files_opened_by_script"])
        self.assertNotIn(
            "synthetic-bearer-value",
            redact_text("Authorization: Bearer synthetic-bearer-value"),
        )


if __name__ == "__main__":
    unittest.main()
