#!/usr/bin/env python3
"""Build audited, source-only uOS27 themes for native non-shell UI.

The Maliit variant targets externally installed QML and can be tested later
using a separate bounded trial. The System Settings variant is SOURCE ONLY:
the app embeds its QML in a compiled Qt resource and needs an ARM64 build.
This tool never installs, binds, restarts services or changes a source tree.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil

from lomiri_glass import read_regular, safe_path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "shell/uos27-native/keyboard/uOS27.json"
DARK_THEME = ROOT / "shell/uos27-native/keyboard/uOS27-Dark.json"
SOURCE_REVISIONS = {
    "keyboard": {
        "repository": "https://gitlab.com/ubports/development/core/lomiri-keyboard.git",
        "commit": "85e1a77b2653f8cd28d8bd1308dbd6c577713892",
        "files": {
            "qml/Keyboard.qml": "3c9fe846d40bfa53be607afc5bf2d3ee5df037602b3e1a95ea54129a0ee7c1ea",
            "qml/keys/CharKey.qml": "84fbf115fc23a26275942774aa338037e54727311a9387c57f8159266e41026a",
            "qml/keys/key_constants.js": "ac5be67c4c481f6301d524081659a11cef2c5eb8c3f4b2b67c0b5ad716a78b57",
        },
    },
    "settings": {
        "repository": "https://gitlab.com/ubports/development/core/lomiri-system-settings.git",
        "commit": "2f4654cf8b32eac7d553910003d1072dfb6d11b3",
        "files": {
            "src/qml/MainWindow.qml": "a593bb65b61b52b182acc44e7045257c7a406b0703b7a7c82e64f82b9b4c067b",
            "src/qml/EntryComponentGrid.qml": "3fab7ecd01a80169e20250250640335c768302245607e8363cc1620bdc2b8c49",
            "src/qml/CategorySection.qml": "faf7f5beec58ef66125f6aa3947ef0952775154160be7b6f727ede22eaae3a19",
            "src/SystemSettings/SettingsItemTitle.qml": "17ad120e82db13b67a6388ab06cad5b9ae998d94cb7708d567ae5775d19c7174",
            "src/SystemSettings/ItemPage.qml": "7762261b9fb406c4c0dfa472e3c11befb4bf3baecc483fc93442c83ff139dff3",
            "src/SystemSettings/ListItems/Standard.qml": "8b1d57c3759be1ea70dd5758a2a442c54902933ba6de6c9115939a721a075f5c",
            "src/SystemSettings/ListItems/Icon.qml": "6ea7efde92d937f7f76f76f9b7a2a43a3a2b7ef77557e49c861cc7c2fc5fbd68",
        },
    },
}


class ThemeError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_one(data: str, before: str, after: str, label: str) -> str:
    if data.count(before) != 1:
        raise ThemeError(f"The audited {label} source structure changed")
    return data.replace(before, after)


def keyboard_transform(name: str, original: str) -> str:
    if name == "qml/Keyboard.qml":
        # Preserve Maliit's selected light/dark family when the user changes
        # the keyboard's own appearance in native Settings.
        theme_choice = ('["SuruDark", "SuruBlack", "JustBlack", "JustGrey", '
                        '"BorderedBlack", "BorderedGrey"].indexOf(')
        result = replace_one(original,
            'Component.onCompleted: Theme.load(maliit_input_method.theme)',
            'Component.onCompleted: Theme.load('
            + theme_choice + 'maliit_input_method.theme) !== -1 ? "uOS27-Dark" : "uOS27")', name)
        return replace_one(result, 'onThemeChanged: Theme.load(target.theme)',
            'onThemeChanged: Theme.load('
            + theme_choice + 'target.theme) !== -1 ? "uOS27-Dark" : "uOS27")', name)
    if name == "qml/keys/CharKey.qml":
        result = replace_one(original, 'radius: units.dp(4)',
                             'radius: units.dp(9)', name)
        return replace_one(result,
            'font.pixelSize: fontSize\n                font.weight: Font.Light',
            'font.pixelSize: fontSize\n                font.weight: Font.Normal', name)
    if name == "qml/keys/key_constants.js":
        return replace_one(original, 'var phoneRowMarginPortrait = 7; // dp',
                           'var phoneRowMarginPortrait = 9; // dp', name)
    raise ThemeError("Unknown keyboard target")


def settings_transform(name: str, original: str) -> str:
    if name == "src/qml/MainWindow.qml":
        return replace_one(original,
            'applicationName: "lomiri-system-settings"',
            'applicationName: "lomiri-system-settings"\n'
            '    // Native dark palette cascades to the existing Settings plugin pages.\n'
            '    theme.name: "Lomiri.Components.Themes.SuruDark"', name)
    if name == "src/qml/EntryComponentGrid.qml":
        result = replace_one(original, '    AbstractButton {\n        id: button',
            '    // The rounded card is decorative. The original AbstractButton\n'
            '    // retains ownership of the click and all accessibility events.\n'
            '    Rectangle {\n'
            '        id: uos27Card\n'
            '        z: -1\n'
            '        anchors.fill: parent\n'
            '        anchors.margins: units.gu(0.2)\n'
            '        radius: units.gu(2)\n'
            '        color: button.pressed ? "#53698b" : "#283750"\n'
            '        border.width: units.dp(1)\n'
            '        border.color: "#526480"\n'
            '        Behavior on color { ColorAnimation { duration: 135 } }\n'
            '    }\n\n'
            '    AbstractButton {\n        id: button', name)
        return replace_one(result, '            fontSize: "small"',
                           '            fontSize: "small"\n'
                           '            color: "#f1f5ff"', name)
    if name == "src/qml/CategorySection.qml":
        # The native plugin manager and its clicked/selected bindings stay
        # untouched; tighten only the grid rhythm and remove legacy rules.
        result = replace_one(original, '    spacing: units.gu(1)',
                             '    spacing: units.gu(1.3)', name)
        result = replace_one(result, '        gridRowSpacing: units.gu(3)',
                             '        gridRowSpacing: units.gu(1.7)', name)
        return replace_one(result,
            '        visible: header.visible && container.layout == "grid"',
            '        visible: false // uOS27 rounded cards separate entries visually', name)
    if name == "src/SystemSettings/SettingsItemTitle.qml":
        result = replace_one(original, '        font.bold: true',
                             '        font.bold: false\n'
                             '        color: "#b2c0d9"', name)
        return replace_one(result, '    height: units.gu(6)',
                           '    height: units.gu(6.5)', name)
    if name == "src/SystemSettings/ItemPage.qml":
        # All native plugin page actions, headers, signal connections, and
        # navigation remain original. Only their backing content is tinted.
        return replace_one(original,
            'Page {\n    id: root\n',
            'Page {\n    id: root\n\n'
            '    Rectangle {\n'
            '        objectName: "uos27SettingsContentBackground"\n'
            '        anchors.fill: parent\n'
            '        z: -1\n'
            '        color: "#121a29"\n'
            '    }\n', name)
    if name == "src/SystemSettings/ListItems/Standard.qml":
        result = replace_one(original, '    divider.colorFrom: theme.palette.normal.base',
                             '    divider.colorFrom: "#29364c"', name)
        return replace_one(result, '    divider.colorTo: theme.palette.normal.base',
                           '    divider.colorTo: "#29364c"', name)
    if name == "src/SystemSettings/ListItems/Icon.qml":
        # Backing sits *behind* the original icon. The native Icon preserves
        # its source/color and the parent Standard keeps its click behavior.
        result = replace_one(original,
            '        height: units.gu(2.5)\n        SlotsLayout.position: SlotsLayout.First',
            '        height: units.gu(3.4)\n'
            '        SlotsLayout.position: SlotsLayout.First\n'
            '        Rectangle {\n'
            '            z: -1\n'
            '            anchors.fill: parent\n'
            '            anchors.margins: -units.gu(0.28)\n'
            '            radius: units.gu(1.05)\n'
            '            color: "#3c5578"\n'
            '            border.width: units.dp(1)\n'
            '            border.color: "#6580a4"\n'
            '        }', name)
        return result
    raise ThemeError("Unknown Settings target")


def build_component(kind: str, source: Path, dest: Path) -> dict:
    spec = SOURCE_REVISIONS[kind]
    mapping = {}
    for relative, expected in sorted(spec["files"].items()):
        src = source / relative
        actual = read_regular(src)
        if sha(actual) != expected:
            raise ThemeError(f"Unrecognized {kind} source: {relative}")
        decoded = actual.decode("utf-8")
        revised = (keyboard_transform if kind == "keyboard" else settings_transform)(relative, decoded)
        if revised == decoded:
            raise ThemeError(f"No visual change for {relative}")
        encoded = revised.encode("utf-8")
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        mapping[relative] = {"original_sha256": expected, "prepared_sha256": sha(encoded)}
    return mapping


def build_patch(source: Path, changed_root: Path, names: list[str]) -> str:
    lines = []
    for name in sorted(names):
        before = read_regular(source / name).decode("utf-8").splitlines(keepends=True)
        after = read_regular(changed_root / name).decode("utf-8").splitlines(keepends=True)
        lines.extend(difflib.unified_diff(before, after,
                     fromfile="a/" + name, tofile="b/" + name, n=3))
    return "".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyboard-source", type=Path, required=True,
                        help="exact upstream lomiri-keyboard checkout")
    parser.add_argument("--settings-source", type=Path, required=True,
                        help="exact upstream lomiri-system-settings checkout")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    keyboard_source = safe_path(args.keyboard_source)
    settings_source = safe_path(args.settings_source)
    output = safe_path(args.output)
    if output.exists():
        parser.error("Refusing to replace an existing preparation")
    for source in (keyboard_source, settings_source):
        if not source.is_dir():
            parser.error("Source checkout missing")
    palettes = {}
    for palette in (THEME, DARK_THEME):
        encoded = read_regular(palette)
        colors = json.loads(encoded)
        if not isinstance(colors, dict) or not all(re.fullmatch("#[0-9a-f]{6}", c)
                for c in (colors["fontColor"], colors["backgroundColor"], colors["charKeyColor"])):
            parser.error("Invalid uOS27 theme palette")
        palettes[palette.name] = encoded
    try:
        output.mkdir(mode=0o755, parents=True, exist_ok=False)
        kb = output / "keyboard"
        settings = output / "system-settings-sources-only"
        keyboard_files = build_component("keyboard", keyboard_source, kb)
        settings_files = build_component("settings", settings_source, settings)
        # The source repository keeps palettes in data/styles; Debian
        # installs them as styles/ below the Maliit plugin QML directory.
        for name, encoded in sorted(palettes.items()):
            target = kb / "styles/lomiri/themes" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded)
            keyboard_files[target.relative_to(kb).as_posix()] = {
                "kind": "new", "prepared_sha256": sha(encoded)
            }
        (output / "keyboard.patch").write_text(
            build_patch(keyboard_source, kb, list(SOURCE_REVISIONS["keyboard"]["files"])),
            encoding="utf-8")
        (output / "system-settings.patch").write_text(
            build_patch(settings_source, settings, list(settings_files)), encoding="utf-8")
        manifest = {
            "schema": 1,
            "name": "uOS27-native-theme",
            "installed": False,
            "hardware_validated": False,
            "system_settings_requires_recompiled_executable": True,
            "keyboard": {**{k: v for k, v in SOURCE_REVISIONS["keyboard"].items() if k != "files"},
                         "files": keyboard_files},
            "system_settings": {**{k: v for k, v in SOURCE_REVISIONS["settings"].items() if k != "files"},
                                "files": settings_files},
        }
        (output / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception:
        # A private output path is caller-selected, but only this invocation's
        # fresh directory is removed after a failed preparation.
        if output.exists():
            shutil.rmtree(output)
        raise
    print(json.dumps({"prepared": str(output), "keyboard_files": len(keyboard_files),
                      "system_settings_source_files": len(settings_files),
                      "installed": False, "hardware_validated": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
