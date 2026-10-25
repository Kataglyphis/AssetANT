"""Asset schema regressions for the production validator."""

import importlib.util
import json
import pathlib
import tempfile
import unittest
from typing import Any

GATE = pathlib.Path(__file__).resolve().parents[1] / "check.py"
SPEC = importlib.util.spec_from_file_location("asset_check", GATE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load asset validator")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class AssetValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = pathlib.Path(temp.name) / "example"
        self.directory.mkdir()
        self.doc: dict[str, Any] = {
            "name": "example",
            "version": 1,
            "file": "example.tar.xz",
            "sha256": "a" * 64,
            "summary": "A sample asset",
            "license": "MIT",
            "attribution": "Example author",
            "origin": None,
            "notes": "",
            "source": {"repository": "https://example.test/repo", "commit": "b" * 40,
                       "path": "Resources/models/example"},
            "unpacked": {"files": 1, "bytes": 2},
        }

    def validate(self, readme: str = "| `example` |") -> list[str]:
        payload = json.dumps(self.doc, indent=2, ensure_ascii=False) + "\n"
        (self.directory / "asset.json").write_text(payload, encoding="utf-8")
        return CHECK.problems(self.directory, readme)

    def test_valid_asset_has_no_findings(self) -> None:
        self.assertEqual([], self.validate())

    def test_nested_source_and_unpacked_errors_stay_visible(self) -> None:
        self.doc["source"]["path"] = "elsewhere/example"
        self.doc["unpacked"]["bytes"] = 0
        self.assertEqual(
            ["source.path must be Resources/.../example",
             "unpacked must hold positive files and bytes (scripts/pack.sh --record writes them)",
             "is missing from the README's asset table"],
            self.validate(readme="no asset table"),
        )


if __name__ == "__main__":
    unittest.main()
