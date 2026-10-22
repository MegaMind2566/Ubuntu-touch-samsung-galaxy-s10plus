# Samsung S10+ TRRS headset: legacy-routing physical test

**Date:** 2026-10-23 (Europe/Rome; user test reported 2026-10-22 23:04 UTC).
**Device:** Samsung Galaxy S10+ Exynos SM-G975F/DS (`beyond2lte`).
**System:** Ubuntu Touch 24.04 / Halium 12, BOOT 6 with graphics permissions fix 1.

## Controlled experiment

Original installed module: `pulseaudio-modules-droid-30`
`14.2.109-0ubports2~20261008093544.3~4ad1b20+ubports24.04.2`
(`arm64`), with module binary
`/usr/lib/pulse-16.1+dfsg1/modules/module-droid-card-30.so`
SHA-256 `baf1a48df837278f3ed84fa046d4be81ddeb9be06ed65d0f256eea9f79bb7912`.

Headset switch state when inserted: `MECHANICAL=1`, `MICROPHONE=1`,
`HEADPHONE=0`. `Headset` input event device has `EVIOCGSW=0x90`.
The headset includes an integrated microphone (TRRS). Separate headphones
without a microphone (TRS) already played audio with the original configuration.

Preflight found one *paused* sink input (`corked=yes`) belonging to
`maliit-server` keyboard feedback, and **zero active** audio streams. The
revised guarded trial (`ut-s10-trrs-legacy-test-v2.py`) permitted it.

The trial temporarily added the environment
`PULSE_MODULES_DROID_EXTRA_CARD_ARGS=use_legacy_stream_set_parameters=true`
via a transient systemd user drop-in; it did **not** change the installed
binary, vendor files, `touch.pa` or the persistent audio6 service fix.

The module loaded with runtime argument:
`voice_virtual_stream=true output_deep_buffer=false use_legacy_stream_set_parameters=true`.

The test selected `output-wired_headset` for `sink.primary-out`
(`pactl` returned 0), submitted a low-level 0.8 s test tone with `pacat`
(`rc=0`), and the tester **heard the tone in the wired headset and not in
the loudspeaker**.

The test then requested the original `output-speaker` port, removed the
temporary systemd override and restarted PulseAudio. The script verified
`active_port=output-speaker`, `default_sink=sink.primary-out`,
`original_module_unchanged=true`, `removed=true` and `restarted=true`,
and emitted `ripristino: ok=true`.

## Findings and boundaries

- **Verified on hardware:** TRRS playback can be physically routed to the
  headset using the module's legacy stream `set_parameters()` routing
  interface. This rules out an inherent inability of the jack to reproduce
  TRRS headset audio under the tested configuration.
- **Prior controlled comparison:** selecting `output-wired_headset` with
  the default nonlegacy module succeeded as a software operation, but the tone
  was heard from the speaker instead.
- **Source-level explanation:** upstream tag `14.2.109` uses Android
  `create_audio_patch()` by default; earlier HAL logs returned
  `ENOSYS` (38) from this route. The alternative uses legacy
  `set_parameters(routing=...)`. The test validates the latter physically,
  not every HAL function.
- **Not yet verified:** automatic port selection on TRRS insertion/removal,
  microphone on the wired TRRS cable, wired TRS under legacy configuration,
  call earpiece/telephony audio, Bluetooth regression, persistent configuration
  across reboot or normal loudspeaker listening after this specific test.
- **Separate availability issue:** `droid-extevdev.c` in the upstream
  `14.2.109` source requires `SW_HEADPHONE_INSERT` or lineout *and*
  `SW_MICROPHONE_INSERT` to mark `output-wired_headset` available; the
  Galaxy S10+ sets only `SW_MICROPHONE_INSERT` for the inserted TRRS headset.
  The staged source patch changes this detection, but **has not been installed,
  ARM64-compiled, or physically tested**. Do not represent it as a complete
  solution by itself.

## Next experiment

Validate a **reversible** legacy routing configuration and TRRS auto-switch
integration. Keep the audio6 v2 user service and `sink.primary-out`
speaker baseline. Stage each change with verified rollback and no vendor
firmware/library replacement. Check the TRS path, headset mic and Bluetooth
interaction separately before promoting any fix as generally stable.
