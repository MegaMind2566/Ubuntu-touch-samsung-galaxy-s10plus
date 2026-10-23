#!/usr/bin/env python3
"""Samsung S10+ Ubuntu Touch: read-only power/charge/suspend inventory.

Run as a normal user:
    python3 ~/Downloads/ut-s10-energia-diagnosi-v2.py --inventario

Only reads allowlisted kernel/sysfs fields and optional UPower/systemd status.
No privileged commands, suspend request, hardware state change, raw logs,
device serials or IMEI. Does not measure battery life or verify suspend.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import time
import shutil
import subprocess
import sys

VERSION = "2026-10-24.power-inventory-v2"
POWER_PATH = Path("/sys/class/power_supply")
THERMAL_PATH = Path("/sys/class/thermal")
BACKLIGHT_PATH = Path("/sys/class/backlight")
BATTERY_FIELDS = (
    "type", "present", "status", "online", "capacity", "capacity_level",
    "health", "charge_type", "charging_enabled", "voltage_now", "current_now",
    "current_avg", "power_now", "temp", "charge_now", "charge_full",
    "charge_full_design", "energy_now", "energy_full", "energy_full_design",
    "cycle_count", "time_to_empty_now", "time_to_full_now", "input_current_limit",
    "constant_charge_current_max", "usb_type", "scope",
)
BATTERY_COUNT_MAX = 35
BACKLIGHT_FIELDS = ("brightness", "actual_brightness", "max_brightness", "bl_power")
SUSPEND_FIELDS = {
    "state": Path("/sys/power/state"),
    "mem_sleep": Path("/sys/power/mem_sleep"),
    # Deliberately NEVER read wakeup_count: kernel may sleep inside read().
    # autosleep read may block on the PM mutex while autosuspend is busy.
    "suspend_stats_success": Path("/sys/power/suspend_stats/success"),
    "suspend_stats_fail": Path("/sys/power/suspend_stats/fail"),
}
UP_KEYS = {
    "type", "state", "percentage", "online", "power supply", "energy",
    "energy-full", "energy-full-design", "energy-rate", "voltage",
    "time to full", "time to empty", "capacity", "warning-level", "battery-level",
}
RE_SAFE = re.compile(r"^[A-Za-z0-9_.+-]{1,72}$")


def safe_name(text: str) -> str:
    return text if RE_SAFE.fullmatch(text) else "nome_non_valido"


def read_value(path: Path, limit: int = 160) -> str | None:
    """Read only a short single line; missing or denied sysfs attrs are normal."""
    try:
        with path.open("rb") as inp:
            raw = inp.read(limit + 1)
    except (OSError, ValueError):
        return None
    if not raw or len(raw) > limit or b"\x00" in raw:
        return None
    value = raw.decode("utf-8", "replace").strip()
    if "\n" in value or "\r" in value or len(value) > limit:
        return None
    return value


def enumerate_children(base: Path, max_items: int = 120) -> list[Path]:
    try:
        # Sysfs class entries are typically symlinks: that is normal.
        nodes = [p for p in base.iterdir() if p.is_dir() and RE_SAFE.fullmatch(p.name)]
    except OSError:
        return []
    return sorted(nodes, key=lambda p: p.name)[:max_items]


def supplies(base: Path = POWER_PATH) -> list[dict]:
    result = []
    for node in enumerate_children(base, BATTERY_COUNT_MAX):
        fields = {}
        for attr in BATTERY_FIELDS:
            val = read_value(node / attr)
            if val is not None:
                fields[attr] = val
        result.append({"dispositivo": safe_name(node.name), "valori": fields})
    return result


def backlights(base: Path = BACKLIGHT_PATH) -> list[dict]:
    result = []
    for node in enumerate_children(base, 12):
        fields = {}
        for attr in BACKLIGHT_FIELDS:
            val = read_value(node / attr)
            if val is not None:
                fields[attr] = val
        result.append({"dispositivo": safe_name(node.name), "valori": fields})
    return result


def suspend_info(paths: dict[str, Path] = SUSPEND_FIELDS) -> dict:
    result = {}
    for key, path in paths.items():
        val = read_value(path)
        if val is not None:
            result[key] = val
    return result


def thermal_zones(base: Path = THERMAL_PATH) -> list[dict]:
    relevant = ("batt", "bat_", "charger", "chg", "cpu", "gpu", "pmic", "skin", "soc", "ap", "usb", "cp_")
    result = []
    zones = [p for p in enumerate_children(base) if re.fullmatch(r"thermal_zone\d+", p.name)]
    for node in zones:
        typ = read_value(node / "type", 72)
        val = read_value(node / "temp", 32)
        if not typ or val is None or not any(w in typ.lower() for w in relevant):
            continue
        try:
            temp = int(val)
        except ValueError:
            continue
        rec = {"sensore": safe_name(node.name), "tipo": typ, "temperatura_mC": temp}
        if -50000 <= temp <= 200000:
            rec["temperatura_C"] = round(temp / 1000.0, 1)
        result.append(rec)
        if len(result) >= 16:
            break
    return result


def upower_extract(text: str) -> list[dict]:
    result = []
    group = None
    for line in text.splitlines():
        if line.startswith("Device:"):
            dev = line.split(":", 1)[1].strip().rsplit("/", 1)[-1]
            if not dev or not RE_SAFE.fullmatch(dev):
                dev = "dispositivo_upower"
            group = {"dispositivo": dev, "valori": {}}
            if len(result) < 12:
                result.append(group)
            else:
                group = None
        elif group is not None and ":" in line:
            key, value = (x.strip() for x in line.split(":", 1))
            if key.lower() in UP_KEYS and len(value) <= 80 and "\x00" not in value:
                group["valori"][key] = value
    return result


def run_optional(cmd: list[str], seconds: int = 5) -> str | None:
    if not shutil.which(cmd[0]):
        return None
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, timeout=seconds,
                           text=True, errors="replace", env={**os.environ, "PAGER": "cat", "SYSTEMD_PAGER": "cat"})
    except (OSError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def power_services() -> dict:
    units = ("upower.service", "repowerd.service", "powerd.service")
    statuses = {}
    for unit in units:
        out = run_optional(["systemctl", "--system", "--no-pager", "show", unit,
                            "-p", "LoadState", "-p", "ActiveState"], seconds=1)
        if out:
            attrs = dict(x.strip().split("=", 1) for x in out.splitlines() if "=" in x)
            statuses[unit] = {k: attrs[k] for k in ("LoadState", "ActiveState") if k in attrs}
    return statuses


def read_uptime() -> float | None:
    raw = read_value(Path("/proc/uptime"), 80)
    if raw is None:
        return None
    try:
        return round(float(raw.split()[0]), 1)
    except (IndexError, ValueError):
        return None


# Each class of hardware reads runs in its OWN subprocess. A vendor sysfs
# read can block inside the kernel; a timer in the same Python process is not
# a reliable protection. The parent NEVER performs such a read itself.
# Parent timeouts use bounded wait, and never block waiting for a D-state child.
SECTION_SECONDS = {
    "uptime_secondi": 2,
    "alimentazione": 6,
    "gestione_sospensione": 3,
    "retroilluminazione": 3,
    "termiche": 5,
    "upower": 5,
    "servizi_energetici": 5,
}


def worker_collect(section: str):
    if section == "uptime_secondi":
        return read_uptime()
    if section == "alimentazione":
        return supplies()
    if section == "gestione_sospensione":
        return suspend_info()
    if section == "retroilluminazione":
        return backlights()
    if section == "termiche":
        return thermal_zones()
    if section == "upower":
        raw = run_optional(["upower", "-d"], seconds=3)
        return upower_extract(raw) if raw is not None else "non_disponibile"
    if section == "servizi_energetici":
        return power_services()
    raise ValueError("Sezione sconosciuta")


def bounded_subprocess(cmd: list[str], seconds: float) -> tuple[str | None, str | None]:
    """Read one child's result; never indefinitely wait for a stuck sysfs read.

    A killed child in uninterruptible kernel sleep may survive momentarily;
    the parent avoids `with Popen` and unbounded `wait` for that reason.
    """
    proc = None
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                close_fds=True, start_new_session=True)
        try:
            stdout, _ = proc.communicate(timeout=seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.communicate(timeout=0.15)
            except subprocess.TimeoutExpired:
                pass
            return None, "limite_tempo"
        if proc.returncode:
            return None, "sezione_non_disponibile"
        if len(stdout) > 250000:
            return None, "output_eccessivo"
        return stdout.decode("utf-8", "replace"), None
    except OSError:
        return None, "processo_non_disponibile"
    except KeyboardInterrupt:
        if proc is not None and proc.poll() is None:
            proc.kill()
        raise
    finally:
        if proc is not None:
            # Closing our ends of the pipes never waits for child exit.
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()
            if proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass


def collect() -> dict:
    started = time.monotonic()
    report = {
        "versione": VERSION,
        "evento": "inventario_energia",
        "orario_locale": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lettura_sola": True,
        "sudo_richiesto": False,
        "sospensione_forzata": False,
        "gestione_sospensione_campi_omessi": ["wakeup_count", "autosleep"],
        "avvisi": {},
    }
    for section, seconds in SECTION_SECONDS.items():
        print("Verifica di sola lettura: " + section + " ...", file=sys.stderr, flush=True)
        raw, err = bounded_subprocess(
            [sys.executable, "-S", str(Path(__file__).resolve()), "--_worker", section],
            seconds=seconds)
        if err is not None:
            report[section] = "non_disponibile"
            report["avvisi"][section] = err
            continue
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or envelope.get("sezione") != section:
                raise ValueError("Sezione inattesa")
            report[section] = envelope["valore"]
        except (ValueError, KeyError, TypeError):
            report[section] = "non_disponibile"
            report["avvisi"][section] = "risposta_non_valida"
    report["tempo_esecuzione_secondi"] = round(time.monotonic() - started, 2)
    report["nota"] = ("Inventario limitato: non prova ricarica, autonomia, "
                       "sospensione o risveglio. Campi di sospensione potenzialmente "
                       "bloccanti intenzionalmente omessi. Nessuna seriale o log privato.")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="S10+ lettura sicura batteria/ricarica/standby")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--inventario", action="store_true")
    actions.add_argument("--_worker", choices=SECTION_SECONDS.keys(), help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args._worker:
            # Child process: only this path reads the kernel power attributes.
            val = worker_collect(args._worker)
            print(json.dumps({"sezione": args._worker, "valore": val}, ensure_ascii=True))
            return 0
        report = collect()
    except KeyboardInterrupt:
        print("UT_S10_ENERGIA " + json.dumps({"evento": "interrotto", "nessuna_modifica": True}))
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print("UT_S10_ENERGIA " + json.dumps({"evento": "errore_inventario", "tipo": type(exc).__name__}))
        return 1
    print("UT_S10_ENERGIA " + json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
