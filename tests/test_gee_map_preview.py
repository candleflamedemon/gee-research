"""Offline layer, failure isolation and categorical-display tests; no fake map is delivered."""
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from gee_map_preview import load_folium_backend, save_interactive_map


class BackendTests(unittest.TestCase):
    def test_backend_selection_is_restored(self):
        backend = SimpleNamespace(Map=Map)
        with patch.dict(os.environ, {"USE_FOLIUM": "original"}), patch(
            "gee_map_preview.importlib.import_module", return_value=backend
        ):
            self.assertIs(load_folium_backend(), backend)
            self.assertEqual(os.environ["USE_FOLIUM"], "original")

    def test_failed_import_restores_environment(self):
        original = os.environ.pop("USE_FOLIUM", None)
        try:
            with patch("gee_map_preview.importlib.import_module", side_effect=ImportError("missing")):
                with self.assertRaises(ImportError):
                    load_folium_backend()
            self.assertNotIn("USE_FOLIUM", os.environ)
        finally:
            if original is not None:
                os.environ["USE_FOLIUM"] = original

    def test_preloaded_package_namespace_is_restored(self):
        original_dictionary = {"OpenStreetMap": "display"}
        package = SimpleNamespace(basemaps=original_dictionary)
        real_submodule = SimpleNamespace(xyz_to_folium=lambda: {})
        backend = SimpleNamespace(Map=Map)
        def resolve(name):
            if name == "geemap.basemaps":
                return real_submodule
            self.assertIs(package.basemaps, real_submodule)
            return backend
        with patch.dict(sys.modules, {"geemap": package}), patch(
            "gee_map_preview.importlib.import_module", side_effect=resolve
        ):
            self.assertIs(load_folium_backend(), backend)
            self.assertIs(package.basemaps, original_dictionary)


class ROI:
    def style(self, **kwargs):
        assert kwargs["fillColor"] == "00000000"
        return "BOUNDARY_DISPLAY"


class Image:
    def remap(self, values, indices):
        return ("DISPLAY_ONLY", values, indices)


class Map:
    def __init__(self, **kwargs):
        self.options = kwargs
        self.layers = []
        self.control = False
        self.legend = None
    def centerObject(self, roi, zoom):
        self.roi = roi
    def addLayer(self, *args):
        self.layers.append(args)
    def add_legend(self, **kwargs):
        self.legend = kwargs
    def add_colorbar(self, *args, **kwargs):
        self.legend = args
    def add_layer_control(self):
        self.control = True
    def get_root(self):
        return self
    def render(self):
        return "<html>OFFLINE TEST ONLY</html>"


class MapTests(unittest.TestCase):
    def kwargs(self, root):
        return dict(roi=ROI(), reference_image=Image(), result_image=Image(),
                    reference_vis={"bands": ["B4", "B3", "B2"], "min": 0, "max": 0.3},
                    result_vis={"bands": ["NDVI"], "min": -1, "max": 1, "palette": ["red", "green"]},
                    output_path=Path(root) / "preview" / "map.html", open_browser=False)
    def test_required_layers_and_no_reinitialization(self):
        with tempfile.TemporaryDirectory() as root:
            made = []
            def factory(**kwargs):
                m = Map(**kwargs); made.append(m); return m
            r = save_interactive_map(**self.kwargs(root), coverage_image=Image(),
                                     coverage_vis={"min": 0, "max": 1}, map_factory=factory)
            self.assertTrue(r["map_generated"])
            self.assertFalse(made[0].options["ee_initialize"])
            self.assertEqual(len(made[0].layers), 4)
            self.assertTrue(made[0].control)
    def test_class_remap_only_display(self):
        with tempfile.TemporaryDirectory() as root:
            made = []
            def factory(**kwargs):
                m=Map(**kwargs); made.append(m); return m
            r=save_interactive_map(**self.kwargs(root), class_values=[10, 50],
                                  class_legend={"Forest": "green", "Urban": "red"}, map_factory=factory)
            self.assertTrue(r["map_generated"])
            self.assertEqual(made[0].layers[1][0][0], "DISPLAY_ONLY")
            self.assertIsNotNone(made[0].legend)
    def test_missing_geemap_requires_consent_and_does_not_run_fallback(self):
        with tempfile.TemporaryDirectory() as root, patch("gee_map_preview.importlib.import_module", side_effect=ImportError("missing")):
            fallback=Mock()
            r=save_interactive_map(**self.kwargs(root), static_fallback=fallback, allow_static_fallback=True)
            self.assertEqual(r["state"], "GEEMAP_INSTALL_CONFIRMATION_REQUIRED")
            self.assertFalse(r["map_generated"])
            self.assertEqual(r["environment"]["python_executable"], sys.executable)
            self.assertFalse(r["environment"]["installation_performed"])
            fallback.assert_not_called()
            self.assertFalse((Path(root)/"preview").exists())
    def test_existing_html_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            kwargs=self.kwargs(root); output=kwargs["output_path"]
            output.parent.mkdir(); output.write_text("original")
            r=save_interactive_map(**kwargs, map_factory=Map)
            self.assertEqual(r["state"], "MAP_CONFLICT")
            self.assertEqual(output.read_text(), "original")
    def test_render_failure_keeps_core_success_and_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            def fail(**kwargs): raise RuntimeError("render failed")
            r=save_interactive_map(**self.kwargs(root), map_factory=fail, static_fallback=lambda: {"ok": True}, allow_static_fallback=True)
            self.assertEqual(r["state"], "MAP_FAILED")
            self.assertTrue(r["static_preview"]["ok"])
    def test_generated_map_is_opened_when_requested(self):
        with tempfile.TemporaryDirectory() as root, patch("gee_map_preview.webbrowser.open", return_value=True) as browser:
            kwargs=self.kwargs(root); kwargs["open_browser"]=True
            r=save_interactive_map(**kwargs, map_factory=Map)
            self.assertTrue(r["browser_open_requested"])
            browser.assert_called_once()
    def test_no_fallback_without_user_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            def fail(**kwargs): raise RuntimeError("render failed")
            fallback=Mock()
            r=save_interactive_map(**self.kwargs(root), map_factory=fail, static_fallback=fallback)
            self.assertEqual(r["state"], "MAP_FAILED")
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
