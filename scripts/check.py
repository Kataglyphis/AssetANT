#!/usr/bin/env python3
"""Validates every assets/<name>/asset.json, and that the README's table lists each asset."""
import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
KEYS = ["name", "version", "file", "sha256", "summary", "license", "attribution", "origin", "notes", "source", "unpacked"]


def identity_problems(doc: dict[str, Any], directory: pathlib.Path) -> list[str]:
    found = []
    name = doc["name"]
    if name != directory.name or not NAME.match(name):
        found.append(f"name {name!r} must equal its directory {directory.name!r} and be a plain file name")
    if not isinstance(doc["version"], int) or isinstance(doc["version"], bool) or doc["version"] < 1:
        found.append("version must be an integer >= 1")
    if doc["file"] != f"{name}.tar.xz":
        found.append(f"file must be {name}.tar.xz")
    if not isinstance(doc["sha256"], str) or not HEX64.match(doc["sha256"]):
        found.append("sha256 must be 64 lowercase hex digits (scripts/pack.sh --record writes it)")
    return found


def text_problems(doc: dict[str, Any]) -> list[str]:
    found = []
    for key in ("summary", "license", "attribution"):
        value = doc[key]
        if not isinstance(value, str) or not value.strip() or "\n" in value:
            found.append(f"{key} must be one non-empty line ('unknown' when nothing is known)")
    if doc["origin"] is not None and (not isinstance(doc["origin"], str) or not doc["origin"].strip()):
        found.append("origin must be null or a non-empty string")
    if not isinstance(doc["notes"], str) or "\n" in doc["notes"]:
        found.append("notes must be one line, possibly empty")
    return found


def source_problems(source: Any, name: str) -> list[str]:
    if not isinstance(source, dict) or list(source) != ["repository", "commit", "path"]:
        return ["source must hold repository, commit and path"]
    found = []
    if not str(source["repository"]).startswith("https://"):
        found.append("source.repository must be an https URL")
    if not HEX40.match(str(source["commit"])):
        found.append("source.commit must be a full 40-digit commit")
    if not str(source["path"]).startswith("Resources/") or not str(source["path"]).endswith(f"/{name}"):
        found.append(f"source.path must be Resources/.../{name}")
    return found


def unpacked_problems(unpacked: Any) -> list[str]:
    if (
        not isinstance(unpacked, dict)
        or list(unpacked) != ["files", "bytes"]
        or not all(isinstance(unpacked[k], int) and unpacked[k] > 0 for k in ("files", "bytes"))
    ):
        return ["unpacked must hold positive files and bytes (scripts/pack.sh --record writes them)"]
    return []


def problems(directory: pathlib.Path, readme: str) -> list[str]:
    spec = directory / "asset.json"
    if not spec.is_file():
        return ["has no asset.json"]
    raw = spec.read_text(encoding="utf-8")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as error:
        return [f"is not JSON: {error}"]
    found = []
    # jq's layout, so `pack.sh --record` never rewrites a file it did not change.
    if raw != json.dumps(doc, indent=2, ensure_ascii=False) + "\n":
        found.append("is not laid out as `jq .` writes it")
    if list(doc) != KEYS:
        found.append(f"keys are {list(doc)}, expected {KEYS} in that order")
        return found
    found.extend(identity_problems(doc, directory))
    found.extend(text_problems(doc))
    found.extend(source_problems(doc["source"], doc["name"]))
    found.extend(unpacked_problems(doc["unpacked"]))
    if f"| `{doc['name']}` |" not in readme:
        found.append("is missing from the README's asset table")
    return found


def main() -> int:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    directories = sorted(p for p in (ROOT / "assets").iterdir() if p.is_dir())
    if not directories:
        print("no assets/<name> directories: nothing checked is a failure, not a pass")
        return 1
    failed = 0
    for directory in directories:
        for problem in problems(directory, readme):
            print(f"assets/{directory.name}: {problem}")
            failed += 1
    print(f"{len(directories)} assets, {failed} problem(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
