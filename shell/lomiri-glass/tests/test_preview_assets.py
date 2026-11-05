#!/usr/bin/env python3
"""Reject absent SVG support or unreadable art before accepting Home renders."""
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "preview"))
from render_shell import require_svg_renderer, validate_demo_icon


class PreviewAssets(unittest.TestCase):
    def test_missing_svg_support_is_a_hard_failure(self):
        class PngOnly:
            @staticmethod
            def supportedImageFormats(): return [b"png"]
        with self.assertRaisesRegex(RuntimeError, "libqt5svg5"):
            require_svg_renderer(PngOnly)

    def test_real_svg_decoder_accepts_authored_vector(self):
        require_svg_renderer()
        with tempfile.TemporaryDirectory(prefix="uos27-svg-check-") as scratch:
            icon = Path(scratch) / "fixture.svg"
            icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" rx="15" fill="#32bc62"/></svg>', encoding="utf-8")
            validate_demo_icon(icon)

    def test_unreadable_icon_is_a_hard_failure(self):
        with tempfile.TemporaryDirectory(prefix="uos27-svg-bad-") as scratch:
            icon = Path(scratch) / "fixture.svg"
            icon.write_text("unreadable vector", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "fixture.svg"):
                validate_demo_icon(icon)


if __name__ == "__main__":
    unittest.main()
