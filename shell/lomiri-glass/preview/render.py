#!/usr/bin/env python3
"""Render the native QML with explicit simulated service state, using Qt 5."""

import argparse
import json
from pathlib import Path

from PyQt5.QtTest import QTest

from runtime import create_view, save_screenshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/lomiri-glass"))
    args = parser.parse_args()
    app, view, backend = create_view()
    captures = []
    for width, height in [(360, 780), (412, 915), (780, 360)]:
        view.resize(width, height)
        QTest.qWait(100)
        captures.append(save_screenshot(view, args.output / f"controls-{width}x{height}.png"))
    print(json.dumps({
        "evidence": "Qt 5 desktop software rendering, fixture service states; not handset execution",
        "screenshots": captures,
    }, indent=2))
    view.close()


if __name__ == "__main__":
    main()
