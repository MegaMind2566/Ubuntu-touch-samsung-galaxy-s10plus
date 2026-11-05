# uOS27 product context

This is a scoped native-shell project within the Galaxy S10+ Ubuntu Touch port.
It does not define the visual identity or requirements of the whole repository.

## Platform and stack

Native Linux / Ubuntu Touch 24.04, Lomiri, Qt Quick 2.15 and existing Ayatana,
GSettings and LightDM interfaces. Impeccable has no native-Linux platform enum;
its native accessibility, layout and state guidance is adapted to this surface.
No React layer replaces the shell.

## Confirmed brief

The user requested the closest practical iOS 27 visual and interaction match:
Home, dock, lock/unlock, Control Center, notifications, gestures, animations,
settings and real Ubuntu services. Adaptive brightness is missing from the port
and must become a real hardware capability rather than a simulated switch.

The prior RC7/uOS27 v015 project is real. Its source was recovered from historical
branch commit `285aef5d3d7a5678dc5812499aa1bf1cc2f0f618`. Later tester evidence
rejected its appearance, upper-screen-only controls and retained Lomiri drawer,
and reported brightness state starting at zero. Bluetooth radio control was
observed in that experiment; that does not certify every radio action now.

## Constraints

- Preserve real LightDM authentication, greeter/session behavior and notification
  privacy filtering. Presentation code must not verify credentials itself.
- Native catalog and pinned launcher models remain authoritative. No invented
  installed apps, notifications, connectivity or hardware acknowledgements.
- Hardware state follows service readback; unavailable/pending/error states
  remain explicit. ALS profile presence and a saved preference are insufficient
  to claim working adaptive brightness.
- Keep the S10+ camera safe area. Do not add an artificial iPhone island over it.
- Local work may interpret/render QML using free Qt; new compilations use free
  public GitHub runners. No phone installation or shell replacement is implied.

## Current scope and open work

Recovered native integration and Qt desktop fixtures are source candidates.
No revised Home, unlock, notification or gesture flow has been accepted on this
handset. iOS application compatibility, Apple services, Siri and complete iOS
feature parity are not provided. Device integration, full GPU/blur fidelity,
runtime performance and recovery require separate validation.

The product record derives from the explicit user/parent brief and recovered
source history; as a subagent I did not conduct a separate user interview.
