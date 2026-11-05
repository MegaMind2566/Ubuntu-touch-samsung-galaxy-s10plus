#!/usr/bin/env python3
"""Capture actual recovered Home/CC/lock/notification QML with bounded fixtures.

No D-Bus, LightDM, app launch, credential entry or hardware operation occurs.
The authentication fixture deliberately cannot unlock the simulated cover.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

from runtime import create_view, save_screenshot
from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtQml import qmlRegisterType
from PyQt5.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_home_host import MockAppDrawerModel, MockAppDrawerProxyModel, MockApplications, I18n, Units


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("out/lomiri-glass/shell"))
    args = parser.parse_args()
    app, view, backend = create_view()
    # Appearance fixtures have simulated readbacks, but unavailable hardware
    # actions. They must never make a toggle look like an acknowledged change.
    backend.set_state(**{key: False for key in backend.values if key.endswith("Available")})
    qmlRegisterType(MockAppDrawerModel, "Lomiri.Launcher", 0, 1, "AppDrawerModel")
    qmlRegisterType(MockAppDrawerProxyModel, "Utils", 0, 1, "AppDrawerProxyModel")
    pinned, units, language = MockApplications(view), Units(view), I18n(view)
    captures, checks = [], []
    with tempfile.TemporaryDirectory(prefix="uos27-shell-preview-", ignore_cleanup_errors=True) as tmp:
        fixture = Path(tmp)
        shutil.copytree(Path(__file__).resolve().parents[1] / "qml/Glass", fixture / "Glass")
        shutil.copyfile(Path(__file__).with_name("ShellPreview.qml"), fixture / "ShellPreview.qml")
        module = fixture / "imports/Lomiri/Components"
        module.mkdir(parents=True)
        (module / "qmldir").write_text("module Lomiri.Components\nLomiriShape 1.3 LomiriShape.qml\n", encoding="utf-8")
        (module / "LomiriShape.qml").write_text('''import QtQuick 2.15
Item {
 id: shape
 enum Aspect { Flat }
 enum FillMode { PreserveAspectCrop }
 property string radius: "medium"
 property int aspect: LomiriShape.Flat
 property Item source
 property int sourceFillMode
 onSourceChanged: if (source) { source.parent = shape; source.anchors.fill = shape; }
 Rectangle { anchors.fill: parent; radius: width * 0.23; color: "#83b7e0"; visible: !shape.source || shape.source.status !== Image.Ready }
}
''', encoding="utf-8")
        launch_module = fixture / "imports/Lomiri/Launcher"
        launch_module.mkdir(parents=True)
        (launch_module / "qmldir").write_text("module Lomiri.Launcher\n", encoding="utf-8")
        # Icons are local original demonstration art, never Apple system assets.
        artwork = {
            "dialer": ("#32bc62", '<path d="M21 15l7 9-5 5c4 7 8 11 15 15l5-5 9 7c-4 13-14 12-26 0S8 20 21 15z" fill="white"/>'),
            "messaging": ("#2bbf60", '<path d="M15 18h34v24H29l-10 7v-7h-4z" fill="white"/>'),
            "browser": ("#f6f7fc", '<circle cx="32" cy="32" r="23" fill="#258be2"/><path d="M39 18l-4 18-14 10 7-21z" fill="white"/><path d="M39 18L28 25l7 11z" fill="#ed5a5c"/>'),
            "camera": ("#b8c5d2", '<rect x="12" y="21" width="40" height="29" rx="6" fill="#293446"/><path d="M23 21v-5h18v5" fill="#293446"/><circle cx="32" cy="35" r="11" fill="#7f9ab5"/><circle cx="32" cy="35" r="7" fill="#192f49"/>'),
            "gallery": ("#fafafa", '<g fill="#f67f59"><ellipse cx="32" cy="21" rx="7" ry="13"/><ellipse cx="32" cy="21" rx="7" ry="13" transform="rotate(60 32 32)" fill="#f4c94b"/><ellipse cx="32" cy="21" rx="7" ry="13" transform="rotate(120 32 32)" fill="#73c565"/><ellipse cx="32" cy="21" rx="7" ry="13" transform="rotate(180 32 32)" fill="#48bed2"/><ellipse cx="32" cy="21" rx="7" ry="13" transform="rotate(240 32 32)" fill="#757fda"/><ellipse cx="32" cy="21" rx="7" ry="13" transform="rotate(300 32 32)" fill="#e878ad"/></g>'),
            "settings": ("#8c9caa", '<circle cx="32" cy="32" r="19" fill="none" stroke="#e7edf4" stroke-width="7"/><circle cx="32" cy="32" r="9" fill="#4e6277"/>'),
            "notes": ("#fffef3", '<path d="M0 0h64v19H0z" fill="#f7ca4b"/><path d="M13 30h38m-38 9h38m-38 9h25" stroke="#c0c5c9" stroke-width="2"/>'),
            "calendar": ("#ffffff", '<path d="M0 0h64v15H0z" fill="#e55f55"/><text x="32" y="48" text-anchor="middle" font-family="sans-serif" font-size="35" fill="#1d2938">5</text>'),
            "file-manager": ("#70c3ed", '<path d="M8 19h19l6 6h23v27H8z" fill="#eefaff"/><path d="M8 19v-7h19l6 7" fill="#d6edf7"/>')
        }
        icons = {}
        for key, (color, path) in artwork.items():
            icon = fixture / (key + ".svg")
            icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><defs><clipPath id="edge"><rect width="64" height="64" rx="15"/></clipPath></defs><g clip-path="url(#edge)"><rect width="64" height="64" fill="' + color + '"/>' + path + '</g></svg>', encoding="utf-8")
            icons[key] = icon.as_uri()
        original_init = MockAppDrawerModel.__init__
        def initialize_catalog(self, parent=None):
            original_init(self, parent)
            self.apps = [(app_id, name, icons[app_id]) for app_id, name, _ in self.apps]
        MockAppDrawerModel.__init__ = initialize_catalog
        pinned.apps = [(app_id, name, icons[app_id]) for app_id, name, _ in pinned.apps]
        view.engine().addImportPath(str(fixture / "imports"))
        view.rootContext().setContextProperty("units", units)
        view.rootContext().setContextProperty("LauncherModel", pinned)
        view.rootContext().setContextProperty("i18n", language)
        view.setSource(QUrl.fromLocalFile(str(fixture / "ShellPreview.qml")))
        if view.status() != view.Ready:
            raise RuntimeError("\n".join(error.toString() for error in view.errors()))
        root = view.rootObject()
        for width, height in ((360, 760), (412, 870)):
            view.resize(width, height)
            QTest.qWait(60)
            icons_item = root.findChild(QObject, "previewStatusIcons")
            assert icons_item.x() + icons_item.width() <= width * (1 - root.property("cameraReservedFraction"))
            for state in ("home", "controls", "lock", "notifications", "switcher"):
                root.showSurface(state)
                QTest.qWait(80)
                captures.append(save_screenshot(view, args.output / f"{state}-{width}x{height}.png"))
        root.showSurface("lock")
        root.requestUnlock()
        assert root.property("surface") == "lock"
        assert root.property("challengeRequested") is True
        checks.append("Unlock gesture requests native authentication; preview never verifies a PIN or bypasses cover")
        assert backend.calls == []
        checks.append("Rendering all five surfaces issues no hardware/service actions")
        checks.append("Home uses the production installed-app catalog view and production pinned dock")
        checks.append("Status icons do not intersect the same 27 percent right-side camera reserve as production")
        MockAppDrawerModel.__init__ = original_init
        view.close()
    report = {"evidence": "Actual Qt 5 desktop software rendering; simulated catalog/state/wallpaper, no phone execution", "checks": checks, "screenshots": captures, "surface_scope": {"home": "production GlassHome with catalog fixture", "controls": "production GlassCenter with inert backend", "lock": "composition fixture plus production unlock gesture; native cover captures are separate", "notifications": "production GlassCenter with empty native-host fixture", "switcher": "empty-state layout fixture; native Spread capture is separate"}, "not_validated": ["handset", "real LightDM challenge", "GPU effects", "Lomiri notification service", "full iOS feature parity"]}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "shell-preview.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
