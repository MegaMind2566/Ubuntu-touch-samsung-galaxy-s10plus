# S10+ audio TRRS: automatic insertion and unplug with v4

**Date:** 23 October 2026, handset runtime evidence.  
**Device:** Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`).  
**Build baseline:** Ubuntu Touch 24.04 / Halium 12, BOOT 6 with graphics permission correction 1.

## Preconditions confirmed on the phone

- PulseAudio uses original audio6 v2 drop-in `91-ut-s10-audio6.conf` and persistent legacy route override `93-ut-s10-trrs-legacy.conf`: `PULSE_MODULES_DROID_EXTRA_CARD_ARGS=use_legacy_stream_set_parameters=true`.
- User monitor `ut-s10-trrs-autoswitch.service` is `loaded`, `enabled`, `active` after reboot and reports `VERSION = '2026-10-23.trrs-integrated-4'`.
- `sink.primary-out` is the original droid card output. The previously verified wired TRRS test physically played audio in the headset using legacy routing. The ARM64 binary was not replaced.

## Post-reboot routing evidence (local handset time)

- **08:41:32–08:41:33:** monitor recorded `none → trrs`, with `output-speaker` initially and requested `output-wired_headset`; after jack insertion, read-only `pactl list sinks` showed `sink.primary-out` `Active Port: output-wired_headset`.
- **08:49:47–08:49:48:** monitor recorded `trrs → none`, observed `output-wired_headset` and requested `output-speaker`; 4 seconds after unplugging, `pactl list sinks` confirmed `Active Port: output-speaker`, and kernel extcon was `MECHANICAL=0 MICROPHONE=0 HEADPHONE=0`.
- **Significant v4 fix validated:** at unplug the monitor saw `default_sink=sink.fast`, yet it still returned **its owned primary-out port** to `output-speaker` without setting the default sink. The previous v3 monitor had failed silent on unplug; this v4 handset test demonstrates return-to-speaker port routing.

## Boundaries and next work

- Verified: a single post-reboot physical TRRS insertion/removal cycle, correct software-port state on both transitions, persistent legacy override and running v4 monitor. Previously, actual sound in wired TRRS earpieces was heard during an on-device legacy-routing trial.
- Not verified in this specific trial: audible speaker playback after unplug, wired TRRS microphone, repeated long-term/reboot cycles, in-app headset icon/label, complete TRS regression, and Bluetooth streaming stability. Do not describe any of these as passing.
- **Outstanding default-sink drift:** `pactl get-default-sink` had earlier changed to `alsa_output.platform-samsung-abox-vdma.stereo-fallback` until the user selected `sink.primary-out`. During this unplug, the monitor observed `sink.fast` as default. Both differ from the verified clean `sink.primary-out`. The monitor intentionally does **not** change default sinks, so this is a separate issue; no cause or durable fix has yet been verified. Avoid forcing defaults while Bluetooth is in use; investigate the source of unintended default-sink switching before promising stability.
