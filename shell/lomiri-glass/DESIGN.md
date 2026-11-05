# uOS27 native direction

Mode: Operate. The reference is iOS 27's refined Liquid Glass, clear hierarchy,
native edge gestures and consistent control geometry, adapted to the S10+.

The recovered visual truth and its failed handset acceptance are the starting
point. Keep source-backed native behavior, replace the cramped layout, and
never turn the shell into a diagnostic dashboard.

## Tokens

- Foreground `#f6f8ff`, secondary foreground `#d7dcec`.
- Cool neutral material; semantic active accents blue for Wi-Fi/Bluetooth and
  green for mobile data. Color changes only follow acknowledged state.
- Large surface radius 3 grid units; small surface radius 2 grid units.
- Primary touch targets at least 44 logical pixels at the default 8 px unit.
- Press 125 ms, entrance 235 ms, exit 180 ms, state transition 170 ms.
- Reduced motion and high contrast remain independently supported.

## Composition and behavior

Home uses four columns in portrait, native installed-app data in row order,
horizontal pages, a pinned four-app dock and in-place search. The restored
column-major GridView arrangement was corrected without replacing its catalog.

Control Center occupies the available surface instead of ending halfway down.
Connectivity, audio, vertical levels and utility destinations share a continuous
material. Display settings distinguish manual level, saved automatic preference
and validated ALS capability. No disabled feature appears enabled by animation.

Lock/unlock belongs to the native cover and LightDM challenge; the numeric
presentation delegates submission and retry/cancel handling. Notifications reuse
Lomiri's profile-filtered model. The desktop preview intentionally contains no
real notification bodies and cannot authenticate or unlock the phone.

## Rendering limits

Production preserves the real wallpaper and underlying app. Desktop screenshots
use an original procedural wallpaper, demonstration app icons/catalog and fixed
time, labeled as fixtures. Qt software rendering does not establish Mali blur,
optical refraction, GPU smoothness or installed-shell fidelity. Fonts use the
available native system face; no Apple font or asset is redistributed.
