# Native QML desktop preview

This harness executes the same `GlassCenter`, `GlassTile`, `GlassSlider` and
`GlassIcon` components used by the shell integration. It supplies explicit
simulated service states, labelled in every screenshot. It does not connect to
D-Bus, read messages, or change the host's Wi-Fi, Bluetooth, brightness or volume.

From the repository root:

```sh
python3 -m venv /tmp/lomiri-glass-qt5
/tmp/lomiri-glass-qt5/bin/pip install -r shell/lomiri-glass/preview/requirements.txt
/tmp/lomiri-glass-qt5/bin/python shell/lomiri-glass/tests/test_qml_surface.py \
  --report out/lomiri-glass/qt5-tests.json
/tmp/lomiri-glass-qt5/bin/python shell/lomiri-glass/preview/render.py \
  --output out/lomiri-glass
```

The Qt software renderer produces portrait previews at 360 × 780 and
412 × 915, and a landscape preview at 780 × 360. The notification host is an
explicit placeholder: production uses the existing Lomiri menu and its native
message actions. No notification-history mock is presented as real output.

The broader component run additionally prepares the exact official upstream
source (26 input hashes plus the local patch/module identities) and renders
native CoverPage/Clock/PIN, populated Notification with privacy mode, and
Spread/WorkspacePreview at 360x760 and 412x870:

```sh
python3 shell/lomiri-glass/preview/prepare_native.py --output out/native-source
python3 shell/lomiri-glass/preview/render_native.py \
  --source out/native-source --output out/lomiri-glass/native
```

Its JSON lists copied native component hashes, assertions and service/theme
boundaries. Mir application textures, notification icons/blur and wallpaper are
synthetic. Successful authentication is never simulated; a fixture response
leaves the greeter locked. The production notification card layout and native
privacy suppression are exercised; live notification delivery is not.

On Ubuntu 24.04 the free distro dependencies are `python3-pyqt5`,
`python3-pyqt5.qtquick`, `qml-module-qtquick2`, `qml-module-qtquick-window2`,
`qml-module-qtqml`, `libqt5svg5` and `fonts-dejavu-core`. QtTest belongs to `python3-pyqt5`;
there is no separate `python3-pyqt5.qttest` package. See the
[official Ubuntu package](https://packages.ubuntu.com/noble/python3-pyqt5).

These tests exercise input, unavailable controls, backend-driven state, automatic
brightness protection, slider value requests, cancellation after native volume
policy decisions and responsive layouts. They do not
establish handset compatibility, D-Bus integration, notification persistence,
GPU performance, battery use or lock-screen behaviour in a live Lomiri session.

After preparing the source overlay, the integration host can also be exercised:

```sh
/tmp/lomiri-glass-qt5/bin/python shell/lomiri-glass/tests/test_panel_host.py \
  --source out/lomiri-glass-prepared-final \
  --report out/lomiri-glass/integration-host-tests.json
```

This runs the actual patched `PanelMenu`, `Showable`, `MenuContent`, `GlassPane`
and UI for both cutout variants. External theme, gesture recognizer, panel-bar
and service interfaces are controlled fixtures. It checks native object/model
preservation during reparenting and unload, tab choice, modal disabling and
indicator disappearance/reappearance. It does not execute the full shell or
physical gesture recognition.
