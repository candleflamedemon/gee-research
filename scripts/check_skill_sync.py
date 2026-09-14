#!/usr/bin/env python3
"""只读比较两份 gee-research 维护文件；不访问网络、环境或认证材料。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT_FILES = {"SKILL.md", "README.md", "LICENSE", ".gitattributes", ".gitignore"}


def maintained_files(root: Path) -> dict[str, str]:
    """只读明确的维护文件类型，避免扫描用户配置、凭据和缓存。"""
    if not root.is_dir() or not (root / "SKILL.md").is_file():
        raise ValueError("Each directory must directly contain SKILL.md")
    paths = [root / name for name in ROOT_FILES]
    paths.append(root / "agents" / "openai.yaml")
    for folder, suffix in (("scripts", ".py"), ("tests", ".py"), ("references", ".md")):
        directory = root / folder
        if directory.is_dir():
            paths.extend(directory.rglob("*" + suffix))
    result = {}
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts[:-1]):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Maintenance files must not link outside the skill directory")
        content = path.read_bytes().replace(b"\r\n", b"\n")
        result[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    return result


def compare_skills(local: Path, release: Path) -> dict:
    left, right = maintained_files(local), maintained_files(release)
    differences = [
        {"path": name, "local_sha256": left[name], "release_sha256": right[name]}
        for name in sorted(left.keys() & right.keys()) if left[name] != right[name]
    ]
    local_only = sorted(left.keys() - right.keys())
    release_only = sorted(right.keys() - left.keys())
    return {"state": "DIFFERENT" if differences or local_only or release_only else "IN_SYNC",
            "local_file_count": len(left), "release_file_count": len(right),
            "local_only": local_only, "release_only": release_only,
            "differences": differences, "newline_normalization": "CRLF to LF",
            "scope": "Skill maintenance files only; not project configuration, credentials or environment"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", required=True, type=Path, help="个人安装Skill目录")
    parser.add_argument("--release", required=True, type=Path, help="待发布副本或下载仓库目录")
    args = parser.parse_args()
    try:
        report = compare_skills(args.local, args.release)
    except (OSError, ValueError):
        # 不回显可能带有本机个人路径的底层异常。
        print(json.dumps({"state": "INPUT_ERROR", "error": "Cannot safely read skill maintenance files"}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["state"] == "IN_SYNC" else 1


if __name__ == "__main__":
    raise SystemExit(main())
