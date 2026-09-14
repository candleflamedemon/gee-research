"""同步检查的离线行为验证；不访问真实认证或科研数据。"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_skill_sync import compare_skills, maintained_files


class SyncTests(unittest.TestCase):
    def pair(self, directory):
        a, b = Path(directory) / "local", Path(directory) / "release"
        for root in (a, b):
            root.mkdir()
            (root / "SKILL.md").write_bytes(b"name: gee-research\n")
            (root / "scripts").mkdir()
            (root / "scripts" / "helper.py").write_bytes(b"print('ok')\n")
        return a, b

    def test_newlines_equal_and_nonmaintenance_files_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.pair(tmp)
            (a / "SKILL.md").write_bytes(b"name: gee-research\r\n")
            (a / "scripts" / "__pycache__").mkdir()
            (a / "scripts" / "__pycache__" / "ignored.py").write_bytes(b"cache")
            (a / ".gee-project.json").mkdir()  # 若误读将发生目录读取错误。
            self.assertEqual(compare_skills(a, b)["state"], "IN_SYNC")
            self.assertEqual(maintained_files(a).keys(), {"SKILL.md", "scripts/helper.py"})

    def test_changes_missing_and_extra_files_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.pair(tmp)
            (a / "scripts" / "helper.py").write_bytes(b"changed")
            (a / "README.md").write_bytes(b"local")
            (b / "LICENSE").write_bytes(b"release")
            report = compare_skills(a, b)
            self.assertEqual(report["state"], "DIFFERENT")
            self.assertEqual(report["local_only"], ["README.md"])
            self.assertEqual(report["release_only"], ["LICENSE"])
            self.assertEqual(report["differences"][0]["path"], "scripts/helper.py")

    def test_invalid_directory_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                maintained_files(Path(tmp))


if __name__ == "__main__":
    unittest.main()
