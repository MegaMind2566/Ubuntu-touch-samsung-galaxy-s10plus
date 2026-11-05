#!/usr/bin/env python3
"""Check consistency of photo-based proposal; cannot verify physical fit."""

import argparse
import json
from pathlib import Path
import re
import unittest


CUTOUT = Path(__file__).resolve().parents[1] / "cutout"


class CutoutProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = json.loads((CUTOUT / "beyond2lte-estimate.json").read_text(encoding="utf-8"))
        cls.snippet = (CUTOUT / "DeviceInfo-keys.snippet").read_text(encoding="utf-8")

    def test_proposal_is_bounded_by_physical_display(self):
        p = self.proposal
        self.assertIn("not-applied", p["status"])
        self.assertEqual(p["physical_display_px"], {"width": 1440, "height": 3040})
        self.assertEqual(p["collapsed_panel_height_px"], p["grid_unit_px"] * 3)
        keys = p["proposed_deviceinfo_values"]
        for name in ("DisplayCutoutsCollapsed", "DisplayCutoutsCollapsedLight", "DisplayCutoutsExpanded"):
            self.assertEqual(len(keys[name]), 1)
            x, y, width, height = map(int, keys[name][0].split())
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertGreater(width, 0)
            self.assertGreater(height, 0)
            self.assertLessEqual(x + width, p["physical_display_px"]["width"])
            self.assertLessEqual(y + height, p["physical_display_px"]["height"])

    def test_photo_envelope_is_contained_with_safety_margin(self):
        hole = self.proposal["basis"]["estimated_physical_hole_envelope_px"]
        x, y, w, h = map(int, self.proposal["proposed_deviceinfo_values"]["DisplayCutoutsCollapsed"][0].split())
        self.assertLessEqual(x + 25, hole["x_min"])
        self.assertGreaterEqual(x + w, hole["x_max"])
        self.assertLessEqual(y, hole["y_min"])
        self.assertGreaterEqual(y + h, hole["y_max"] + 20)
        self.assertEqual(x + w, self.proposal["physical_display_px"]["width"])

    def test_snippet_matches_json_and_cannot_be_mistaken_for_profile(self):
        self.assertIn("NOT a standalone DeviceInfo file", self.snippet)
        self.assertNotRegex(self.snippet, r"(?m)^beyond2lte:\s*$")
        content = [line for line in self.snippet.splitlines() if not line.lstrip().startswith("#") and line.strip()]
        expected = self.proposal["proposed_deviceinfo_values"]
        for key, value in expected.items():
            self.assertEqual(sum(bool(re.fullmatch(r"  " + key + r":(?: \d+)?", line)) for line in content), 1)
            if isinstance(value, int):
                self.assertIn(f"  {key}: {value}", content)
            else:
                self.assertIn(f"  {key}:", content)
                for rect in value:
                    self.assertIn(f"    - {rect}", content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CutoutProposalTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "schema": 1,
        "scope": "Off-device static validation of photograph-based DeviceInfo candidate",
        "tests": result.testsRun,
        "successful": result.wasSuccessful(),
        "handset_validated": False,
        "installed": False,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
