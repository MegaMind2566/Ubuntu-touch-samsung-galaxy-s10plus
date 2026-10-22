#!/usr/bin/env python3
"""Samsung S10+ Ubuntu Touch: guarded TRRS legacy audio + automatic routing.

Intended ONLY for the independently measured beyond2lte phablet baseline.

    python3 ut-s10-trrs-integrato.py --controlla   # read-only
    python3 ut-s10-trrs-integrato.py --installa    # interactive physical test, then persist
    python3 ut-s10-trrs-integrato.py --verifica    # read-only installed-state check
    python3 ut-s10-trrs-integrato.py --ripristina  # remove exactly our own files

No root, no vendor/Android binary edits, no recording, no audio volume changes.
Installing/restoring restarts pulseaudio.service (existing audio6 v2 retained).
The helper routes only the *output* for TRRS; headset mic is NOT verified.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import stat
import struct
import subprocess
import sys
import time

VERSION = '2026-10-23.trrs-integrated-3'
UID = 32011
HOME = Path('/home/phablet')
RUNTIME = Path('/run/user/32011')
SINK, SOURCE = 'sink.primary-out', 'source.primary-in'
SPEAKER, HEADSET, HEADPHONES = 'output-speaker', 'output-wired_headset', 'output-wired_headphone'
LEGACY = 'use_legacy_stream_set_parameters=true'
BASE_ARGS = 'voice_virtual_stream=true output_deep_buffer=false'
PKG_VERSION = '14.2.109-0ubports2~20261008093544.3~4ad1b20+ubports24.04.2'
ORIGINAL = Path('/usr/lib/pulse-16.1+dfsg1/modules/module-droid-card-30.so')
ORIGINAL_SHA = 'baf1a48df837278f3ed84fa046d4be81ddeb9be06ed65d0f256eea9f79bb7912'
AUDIO6 = HOME / '.config/systemd/user/pulseaudio.service.d/91-ut-s10-audio6.conf'
AUDIO6_SHA = 'eb5b101eca0a844f6a1766fab2ca604ffea4f8b21fe7bacb5469e04378fa0c14'
LEGACY_CONF = HOME / '.config/systemd/user/pulseaudio.service.d/93-ut-s10-trrs-legacy.conf'
UNIT_NAME = 'ut-s10-trrs-autoswitch.service'
UNIT_FILE = HOME / '.config/systemd/user' / UNIT_NAME
SCRIPT_FILE = HOME / '.local/libexec/ut-s10-trrs-integrato.py'
UNIT_LINK = HOME / '.config/systemd/user/default.target.wants' / UNIT_NAME
LINK_TARGET = '../' + UNIT_NAME
JACK = Path('/sys/class/extcon/extcon1/state')
LOCK = RUNTIME / 'ut-s10-trrs-integration.lock'
TRIAL = RUNTIME / 'systemd/user/pulseaudio.service.d/94-ut-s10-trrs-integration-trial.conf'
OLDER_TRIAL = RUNTIME / 'systemd/user/pulseaudio.service.d/92-ut-s10-trrs-legacy-trial.conf'
SERVICE = 'pulseaudio.service'

LEGACY_TEXT = ('# Samsung S10+ beyond2lte: physical TRRS routing verified 2026-10-23.\n'
               '# Use Android legacy stream routing instead of unsupported create_audio_patch.\n'
               '[Service]\n'
               'Environment="PULSE_MODULES_DROID_EXTRA_CARD_ARGS=' + LEGACY + '"\n')
UNIT_TEXT = '''# Samsung S10+ TRRS switch controller: phablet user, read-only jack state.
[Unit]
Description=Samsung S10+ TRRS headset automatic output routing (experimental)
Wants=pulseaudio.service
After=pulseaudio.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/phablet/.local/libexec/ut-s10-trrs-integrato.py --monitor
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
Environment=LC_ALL=C
Environment=PULSE_SERVER=unix:/run/user/32011/pulse/native

[Install]
WantedBy=default.target
'''
LEGACY_SHA = hashlib.sha256(LEGACY_TEXT.encode('utf-8')).hexdigest()
TRIAL_TEXT = ('# Temporary legacy route for an unapproved TRRS install test.\n'
              '[Service]\n'
              'Environment="PULSE_MODULES_DROID_EXTRA_CARD_ARGS=' + LEGACY + '"\n')
TRIAL_SHA = hashlib.sha256(TRIAL_TEXT.encode('utf-8')).hexdigest()
UNIT_SHA = hashlib.sha256(UNIT_TEXT.encode('utf-8')).hexdigest()


class GuardError(Exception):
    pass


def emit(event, **data):
    print('UT_S10_TRRS_AUTO ' + json.dumps(dict(event=event, **data),
          ensure_ascii=True, sort_keys=True), flush=True)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exists(path):
    return os.path.lexists(path)


def owned_regular(path, expected_sha=None):
    if not exists(path):
        return False
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != UID or path.is_symlink():
        raise GuardError('File non previsto o proprietario diverso: ' + str(path))
    if expected_sha is not None and sha(path) != expected_sha:
        raise GuardError('File modificato rispetto al pacchetto: ' + str(path))
    return True


def ensure_dirs(path):
    if not path.is_relative_to(HOME):
        raise GuardError('Destinazione fuori dalla home: ' + str(path))
    parts = [HOME]
    for part in path.relative_to(HOME).parts:
        parts.append(parts[-1] / part)
    for p in parts:
        if exists(p):
            st = p.lstat()
            if not stat.S_ISDIR(st.st_mode) or p.is_symlink() or st.st_uid != UID:
                raise GuardError('Directory inattesa: ' + str(p))
        else:
            p.mkdir(mode=0o700)


def create_only(path, data, mode=0o600):
    ensure_dirs(path.parent)
    if exists(path):
        raise GuardError('File gia presente: ' + str(path))
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(path, mode)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def checked_runtime_dir(create=False):
    """Reject symlink redirection and unexpected owners for our /run paths."""
    parts = [RUNTIME, RUNTIME / 'systemd', RUNTIME / 'systemd/user',
             RUNTIME / 'systemd/user/pulseaudio.service.d']
    for p in parts:
        if exists(p):
            st = p.lstat()
            if not stat.S_ISDIR(st.st_mode) or p.is_symlink() or st.st_uid != UID:
                raise GuardError('Directory runtime inattesa: '+str(p))
        elif create:
            p.mkdir(mode=0o700)
    return TRIAL.parent


def create_trial():
    checked_runtime_dir(create=True)
    if exists(TRIAL):
        raise GuardError('Override runtime gia presente: '+str(TRIAL))
    fd = os.open(TRIAL, os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(TRIAL_TEXT.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        TRIAL.unlink(missing_ok=True)
        raise


def trial_present():
    return owned_regular(TRIAL, TRIAL_SHA)


def source_sha():
    here = Path(__file__)
    if not here.is_file() or here.is_symlink() or here.stat().st_size > 200000:
        raise GuardError('Sorgente del gestore inatteso')
    return sha(here)


def paths_state(allow_partial=False):
    """Reject unexpected files; permit partial installation only in rollback."""
    expect = ((LEGACY_CONF, LEGACY_SHA), (UNIT_FILE, UNIT_SHA),
              (SCRIPT_FILE, source_sha()))
    present = {}
    for path, digest in expect:
        present[str(path)] = owned_regular(path, digest)
    if exists(UNIT_LINK):
        if not UNIT_LINK.is_symlink() or os.readlink(UNIT_LINK) != LINK_TARGET:
            raise GuardError('Link di avvio differente: ' + str(UNIT_LINK))
        present[str(UNIT_LINK)] = True
    else:
        present[str(UNIT_LINK)] = False
    if not allow_partial and 0 < sum(present.values()) < len(present):
        raise GuardError('Installazione parziale: utilizzare --ripristina')
    return present


def assert_user():
    if (os.getuid() != UID or os.geteuid() != UID or os.getgid() != UID or
            Path.home() != HOME):
        raise GuardError('Eseguire come phablet senza sudo')
    if not (RUNTIME / 'bus').exists():
        raise GuardError('Bus utente systemd non disponibile')


def baseline():
    assert_user()
    if not ORIGINAL.is_file() or ORIGINAL.is_symlink() or sha(ORIGINAL) != ORIGINAL_SHA:
        raise GuardError('Modulo audio ARM64 differente dal baseline: nessuna modifica')
    if not AUDIO6.is_file() or AUDIO6.is_symlink() or sha(AUDIO6) != AUDIO6_SHA:
        raise GuardError('Fix audio6 v2 differente dal baseline: nessuna modifica')
    ver = output(['/usr/bin/dpkg-query', '-W', '-f=${Version}', 'pulseaudio-modules-droid-30'])
    if ver != PKG_VERSION:
        raise GuardError('Pacchetto audio aggiornato o diverso dal baseline')


def env():
    e = os.environ.copy()
    for k in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'PULSE_SINK', 'PULSE_SOURCE',
              'PULSE_CLIENTCONFIG', 'PULSE_RUNTIME_PATH', 'PULSE_MODULES_DROID_EXTRA_CARD_ARGS'):
        e.pop(k, None)
    e.update(LC_ALL='C', PAGER='cat',
             XDG_RUNTIME_DIR=str(RUNTIME),
             DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(RUNTIME / 'bus'),
             PULSE_SERVER='unix:' + str(RUNTIME / 'pulse/native'))
    return e


def run(cmd, timeout=20, check=True, data=None):
    try:
        p = subprocess.run([str(x) for x in cmd], input=data, capture_output=True,
                           timeout=timeout, env=env(), check=False)
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise GuardError('Comando non riuscito: '+str(cmd[0])) from ex
    if p.returncode and check:
        raise GuardError('{} rc={} {}'.format(cmd[0], p.returncode,
                         p.stderr.decode('utf-8', 'replace').strip()[:160]))
    return p


def output(cmd, **kw):
    return run(cmd, **kw).stdout.decode('utf-8', 'replace').strip()


def ctl(*args, timeout=30, check=True):
    return output(['/usr/bin/systemctl', '--user', *args], timeout=timeout,
                  check=check)


def props(name, names):
    raw = ctl('show', name, '--property='+','.join(names))
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def pulse(*args):
    return output(['/usr/bin/pactl', *args], timeout=10)


def js_pulse(item):
    try:
        rows = json.loads(pulse('--format=json', 'list', item))
    except ValueError as ex:
        raise GuardError('JSON PulseAudio non valido: '+item) from ex
    if not isinstance(rows, list):
        raise GuardError('Struttura JSON PulseAudio errata: '+item)
    return rows


def module_args():
    entries = [x for x in js_pulse('modules')
               if isinstance(x, dict) and x.get('name') == 'module-droid-card-30']
    if len(entries) != 1 or not isinstance(entries[0].get('argument', ''), str):
        raise GuardError('Modulo droid-card-30 non caricato come previsto')
    return entries[0].get('argument', '')


def service():
    p = props(SERVICE, ['ActiveState', 'MainPID', 'Type', 'PrivateUsers',
                        'DropInPaths', 'Environment', 'ExecStart'])
    if p.get('ActiveState') != 'active' or p.get('Type') != 'notify' or p.get('PrivateUsers') != 'yes':
        raise GuardError('Servizio PulseAudio/audio6 non conforme al baseline')
    try:
        if int(p.get('MainPID', '0')) < 2:
            raise GuardError('PulseAudio senza PID valido')
    except ValueError as ex:
        raise GuardError('PID PulseAudio non valido') from ex
    if str(AUDIO6) not in p.get('DropInPaths', '').split():
        raise GuardError('Override audio6 v2 non attivo')
    if '/usr/bin/pulseaudio' not in p.get('ExecStart', ''):
        raise GuardError('Comando di avvio PulseAudio inatteso')
    return p


def sink_obj():
    matches = [x for x in js_pulse('sinks')
               if isinstance(x, dict) and x.get('name') == SINK]
    if len(matches) != 1 or 'module-droid-card' not in str(matches[0].get('driver', '')):
        raise GuardError('sink.primary-out non disponibile')
    return matches[0]


def port_name(value):
    return value.get('name') if isinstance(value, dict) else value


def sink_port():
    return port_name(sink_obj().get('active_port'))


def sink_ports():
    pp = sink_obj().get('ports') or []
    return set(pp) if isinstance(pp, dict) else {
        x.get('name') for x in pp if isinstance(x, dict)
    }


def jack_state():
    try:
        data = dict(line.split('=', 1) for line in JACK.read_text().splitlines()
                    if '=' in line)
    except (OSError, ValueError) as ex:
        raise GuardError('Stato extcon non leggibile') from ex
    vals = tuple(data.get(k) for k in ('MECHANICAL', 'MICROPHONE', 'HEADPHONE'))
    if vals == ('0', '0', '0'):
        return 'none'
    if vals == ('1', '1', '0'):
        return 'trrs'
    if vals == ('1', '0', '1'):
        return 'trs'
    return 'unknown'


def pa_pid():
    p = props(SERVICE, ['ActiveState','MainPID'])
    if p.get('ActiveState') != 'active':
        raise GuardError('PulseAudio non attivo')
    pid = int(p.get('MainPID', '0'))
    if pid <= 1:
        raise GuardError('PID PulseAudio non valido')
    return pid


def paused_streams():
    rows = js_pulse('sink-inputs')
    paused = 0
    for row in rows:
        if not isinstance(row, dict):
            raise GuardError('Flusso audio inatteso')
        v = row.get('corked')
        if isinstance(v, bool):
            corked = v
        elif isinstance(v, str) and v.strip().lower() in ('yes','true','no','false'):
            corked = v.strip().lower() in ('yes','true')
        else:
            raise GuardError('Stato pausa flusso audio ambiguo')
        if not corked:
            raise GuardError('Riproduzione audio attiva: chiudere le app che suonano')
        paused += 1
    return paused


def args_file_guard():
    af = RUNTIME / 'pa_modules_droid_args'
    if exists(af):
        if not af.is_file() or af.is_symlink() or af.stat().st_size > 8192:
            raise GuardError('File deviceinfo args inatteso')
        if 'PULSE_MODULES_DROID_EXTRA_CARD_ARGS' in af.read_text(errors='replace'):
            raise GuardError('Argomenti PulseAudio deviceinfo in conflitto')


def can_configure():
    baseline()
    if exists(TRIAL) or exists(OLDER_TRIAL):
        raise GuardError('Override di prova in /run gia presente: ripristinare il test precedente')
    checked_runtime_dir()
    args_file_guard()
    now = service()
    if str(LEGACY_CONF) in now.get('DropInPaths', '').split():
        raise GuardError('Override legacy gia attivo')
    if 'PULSE_MODULES_DROID_EXTRA_CARD_ARGS=' in now.get('Environment', ''):
        raise GuardError('Configurazione argomenti droid gia presente')
    if module_args() != BASE_ARGS:
        raise GuardError('Modulo con argomenti iniziali diversi dal baseline')
    if pulse('get-default-sink') != SINK or pulse('get-default-source') != SOURCE:
        raise GuardError('Default audio non invariati: nessuna modifica')
    if sink_port() != SPEAKER or not {HEADSET, SPEAKER, HEADPHONES}.issubset(sink_ports()):
        raise GuardError('Porte o uscita predefinita inattese')
    paused = paused_streams()
    st = paths_state()
    if any(st.values()):
        raise GuardError('Gestore gia installato: --verifica o --ripristina')
    return {'pid': int(now['MainPID']), 'paused': paused, 'jack': jack_state()}


def create_files():
    """Create owner-only files without touching any existing files."""
    src = Path(__file__)
    if src.is_symlink() or not src.is_file():
        raise GuardError('Il file scaricato deve essere regolare, non un link')
    create_only(SCRIPT_FILE, src.read_bytes(), 0o600)
    create_only(UNIT_FILE, UNIT_TEXT.encode('utf-8'), 0o600)
    # Keep permanent routing absent until BOTH physical test and consent pass.


def install_link():
    ensure_dirs(UNIT_LINK.parent)
    if exists(UNIT_LINK):
        raise GuardError('Collegamento di servizio gia presente')
    UNIT_LINK.symlink_to(LINK_TARGET)


def check_legacy_loaded():
    a = module_args()
    if LEGACY not in a.split() or not a.startswith(BASE_ARGS):
        raise GuardError('Opzione legacy non caricata: '+a[:140])
    if pulse('get-default-sink') != SINK or pulse('get-default-source') != SOURCE:
        raise GuardError('Default sink/source cambiati dopo il riavvio')
    return a


def wait_pulse(legacy, timeout=30):
    end = time.monotonic() + timeout
    latest = 'attesa'
    while time.monotonic() < end:
        try:
            p = service()
            a = module_args()
            if (LEGACY in a.split()) == legacy:
                if pulse('get-default-sink') != SINK:
                    pulse('set-default-sink', SINK)
                if pulse('get-default-source') != SOURCE or sink_port() != SPEAKER:
                    raise GuardError('Sorgente/uscita non tornate al baseline')
                return int(p['MainPID']), a
            latest = 'argomenti modulo non attesi: ' + a
        except (GuardError, OSError, ValueError) as ex:
            latest = str(ex)
        time.sleep(1)
    raise GuardError('Riavvio PulseAudio non verificato: '+latest[:130])


def tone():
    rate, length = 48000, 38400  # 0.8 seconds
    buf = bytearray()
    for i in range(length):
        fade = min(1.0, i/1200, (length-i-1)/1200)
        n = int(1200 * max(0,fade) * math.sin(2*math.pi*523.25*i/rate))
        buf.extend(struct.pack('<hh',n,n))
    return bytes(buf)


def play_tone():
    p = run(['/usr/bin/pacat', '--raw', '--playback', '--device='+SINK,
             '--format=s16le', '--rate=48000', '--channels=2',
             '--volume=32768', '--stream-name=ut-s10-trrs-auto-tone'],
            data=tone(), timeout=10, check=False)
    emit('tono', rc=p.returncode, bytes_submitted=153600)
    if p.returncode:
        raise GuardError('Riproduzione tono fallita')


def prompt(msg, timeout=180):
    print(msg, flush=True)
    try:
        with open('/dev/tty', 'r', encoding='utf-8', errors='replace') as tty:
            print('> ', end='', flush=True)
            if not select.select([tty], [], [], timeout)[0]:
                raise GuardError('Tempo conferma esaurito; ripristino')
            return tty.readline(32).strip().lower()
    except (OSError, EOFError) as ex:
        raise GuardError('Terminale interattivo non disponibile') from ex


def expect_route(expected_state, expected_port, timeout=16):
    end = time.monotonic()+timeout
    error = 'attesa'
    while time.monotonic() < end:
        try:
            state = jack_state()
            port = sink_port()
            if state == expected_state and port == expected_port:
                emit('route_verificato', jack=state, port=port)
                return
            error='jack='+state+', port='+str(port)
        except GuardError as ex:
            error=str(ex)
        time.sleep(0.5)
    raise GuardError('Routing automatico non confermato: '+error)


def physical_acceptance():
    prompt('Scollega le cuffie cablate e premi Invio; attendo output-speaker.',
           timeout=180)
    expect_route('none', SPEAKER)
    prompt('Inserisci gli auricolari CON MICROFONO (TRRS) e premi Invio.', 180)
    expect_route('trrs', HEADSET)
    if paused_streams() > 2:
        raise GuardError('Nuovi flussi audio inattesi durante prova')
    play_tone()
    answer = prompt('Dove hai sentito il tono? c=cuffie, a=altoparlante, n=nessuna', 90)
    emit('ascolto', heard_headset=answer=='c', heard_speaker=answer=='a', heard_none=answer=='n')
    if answer != 'c':
        raise GuardError('Riproduzione TRRS automatica non confermata')
    prompt('Ora RIMUOVI gli auricolari TRRS e premi Invio.', 180)
    expect_route('none', SPEAKER)
    # Validate no regression of already-working three-contact TRS headphones.
    # Their route is left entirely to PulseAudio's original event handling.
    prompt('Ora inserisci le cuffie SENZA microfono (TRS), poi premi Invio.', 180)
    expect_route('trs', HEADPHONES)
    play_tone()
    answer = prompt('Il tono TRS era nelle cuffie? [s/N]', 90)
    emit('ascolto_trs', headphones=answer in ('s','si'))
    if answer not in ('s', 'si'):
        raise GuardError('Riproduzione TRS non verificata con la modalita legacy')
    prompt('RIMUOVI le cuffie TRS e premi Invio.', 180)
    expect_route('none', SPEAKER)
    play_tone()
    answer = prompt('Il tono finale e uscito dall ALTOPARLANTE? [s/N]', 90)
    emit('ascolto_speaker', speaker=answer in ('s','si'))
    if answer not in ('s', 'si'):
        raise GuardError('Riproduzione speaker non confermata')
    if prompt('Prova TRRS/TRS/speaker superata: mantenere il fix al prossimo riavvio? [s/N]', 90) not in ('s','si'):
        raise GuardError('Installazione permanente non autorizzata: ripristino')


def monitor_routing(kind, current_port, default_sink, is_legacy):
    """Pure decision function; never change other sinks, TRS or an absent headset."""
    if default_sink != SINK or not is_legacy:
        return None
    if kind == 'trrs' and current_port != HEADSET:
        return HEADSET
    if kind == 'none' and current_port == HEADSET:
        return SPEAKER
    return None


def monitor():
    assert_user()
    # Safe to run from a user service. No writes, no privilege escalation.
    if not owned_regular(UNIT_FILE, UNIT_SHA) or not owned_regular(SCRIPT_FILE, source_sha()):
        raise GuardError('File di integrazione non presenti; monitor non avviato')
    if not owned_regular(LEGACY_CONF, LEGACY_SHA) and not trial_present():
        raise GuardError('Nessuna configurazione legacy persistente o temporanea')
    emit('monitor_avvio', version=VERSION, pid=os.getpid(), poll_seconds=1.0,
         controls='solo_uscita_TRRS', volumes_unchanged=True)
    last_raw, consecutive, previous = None, 0, None
    last_problem, logged_at = None, 0.0
    last_inspected_at = 0.0
    # Cheap sysfs read once a second. Contact changes trigger an immediate
    # PulseAudio check after two identical samples (~1 s debounce).
    # At stable state the server is queried at most once per 12 s, keeping
    # systemctl/pactl process launches low on battery-operated hardware.
    while True:
        try:
            kind = jack_state()
            if kind == last_raw:
                consecutive = min(3, consecutive + 1)
            else:
                last_raw, consecutive = kind, 1
                previous = None
            if consecutive < 2 or kind == 'unknown':
                time.sleep(1.0)
                continue
            now = time.monotonic()
            if previous is not None and (now - last_inspected_at) < 12.0:
                time.sleep(1.0)
                continue
            last_inspected_at = now
            pid = pa_pid()
            if kind == 'trs':
                # Original TRS detection and automatic routing remain untouched.
                previous = (kind, pid)
            else:
                args = module_args()
                if LEGACY not in args.split():
                    raise GuardError('Opzione legacy inattiva; monitor in attesa')
                default = pulse('get-default-sink')
                port = sink_port() if default == SINK else None
                route = monitor_routing(kind, port, default, True)
                if route:
                    pulse('set-sink-port', SINK, route)
                    if sink_port() != route:
                        raise GuardError('pactl porta non selezionata: ' + route)
                    emit('commutazione', jack=kind, target=route, pulse_pid=pid)
                # Never replace the user's Bluetooth/A2DP default sink.
                previous = (kind, pid)
            last_problem = None
        except (GuardError, OSError, ValueError) as ex:
            problem = str(ex)[:130]
            now = time.monotonic()
            if problem != last_problem or now - logged_at > 20:
                emit('monitor_attesa', reason=problem)
                logged_at = now
                last_problem = problem
            # Errors should be retried next iteration, not postponed 12 sec.
            previous = None
        time.sleep(1.0)


def verify():
    baseline()
    state = paths_state()
    if not all(state.values()):
        raise GuardError('Installazione assente o incompleta')
    now=service()
    if str(LEGACY_CONF) not in now.get('DropInPaths','').split():
        raise GuardError('Drop-in legacy non applicato a PulseAudio')
    args=check_legacy_loaded()
    m=props(UNIT_NAME,['ActiveState','MainPID'])
    enabled=ctl('is-enabled',UNIT_NAME)
    if m.get('ActiveState')!='active' or int(m.get('MainPID','0'))<2 or enabled!='enabled':
        raise GuardError('Monitor non attivo/abilitato')
    emit('verifica',ok=True,legacy_args=args,original_binary_unchanged=True,
         audio6_unchanged=True,monitor_active=True,monitor_enabled=True,
         sink_port=sink_port(),jack=jack_state(),installed_files=4)


def stop_monitor():
    # A partial install may have written a unit file without daemon-reload.
    # A missing/unloaded unit is safely inactive, not a recovery error.
    ctl('stop', UNIT_NAME, timeout=15, check=False)
    raw = ctl('show', UNIT_NAME, '--property=ActiveState', timeout=12, check=False)
    states = dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    if states.get('ActiveState') == 'active':
        raise GuardError('Monitor TRRS ancora attivo; ripristino sospeso')


def remove_ours(restart_audio=True):
    present=paths_state(allow_partial=True)
    runtime_present=trial_present()
    count=sum(present.values())+int(runtime_present)
    if count==0:
        emit('ripristino',ok=True,already_clean=True,no_changes=True)
        return
    # Stop the monitor FIRST to prevent a race with the speaker restoration.
    if present.get(str(UNIT_FILE)) or present.get(str(UNIT_LINK)):
        stop_monitor()
    # Ask for the physical speaker route while legacy routing is still active.
    # Even on routing failure, carry on with removal/restart for recovery.
    if restart_audio:
        try:
            if LEGACY in module_args().split() and sink_port() == HEADSET:
                pulse('set-sink-port', SINK, SPEAKER)
                if sink_port() != SPEAKER:
                    raise GuardError('Porta speaker non ripristinata')
                emit('speaker_ripristinato', port=SPEAKER)
        except GuardError as ex:
            emit('speaker_ripristino_non_confermato', reason=str(ex)[:110])
    if present.get(str(UNIT_LINK)):
        UNIT_LINK.unlink()
    if runtime_present:
        TRIAL.unlink()
    for p in (UNIT_FILE, LEGACY_CONF, SCRIPT_FILE):
        if present.get(str(p)):
            p.unlink()
    ctl('daemon-reload',timeout=18)
    had_config = runtime_present or present.get(str(LEGACY_CONF), False)
    if restart_audio and had_config:
        ctl('reset-failed',SERVICE,'pulseaudio.socket',timeout=15,check=False)
        ctl('start','pulseaudio.socket',timeout=15,check=False)
        ctl('restart',SERVICE,timeout=45)
        pid,args=wait_pulse(legacy=False,timeout=27)
        if args != BASE_ARGS:
            raise GuardError('Modulo non tornato agli argomenti originali')
        emit('ripristino',ok=True,previous_files_removed=count,
             original_module_unchanged=sha(ORIGINAL)==ORIGINAL_SHA,
             audio6_unchanged=sha(AUDIO6)==AUDIO6_SHA,
             pulse_pid=pid,source=SOURCE,sink=SINK,port=sink_port())
    else:
        emit('ripristino',ok=True,previous_files_removed=count,
             pulse_restart=False)


def install():
    state=can_configure()
    emit('preflight_ok',**state, original_sha=ORIGINAL_SHA,legacy_active=False,
         files_unchanged=True)
    if prompt('PROVA TEMPORANEA: riavvio PulseAudio e test TRRS/TRS/altoparlante. '
              'Persistenza SOLO dopo test positivo e seconda conferma. [s/N]',90) not in ('s','si'):
        emit('annullato',no_changes=True)
        return
    touched=False
    needs_restore_pulse=False
    try:
        touched=True
        create_files()   # Not enabled. Harmless if reboot happens during trial.
        create_trial()   # Only in /run/user; disappears at reboot.
        ctl('daemon-reload',timeout=18)
        sv=service()
        if str(TRIAL) not in sv.get('DropInPaths','').split() or (
            'PULSE_MODULES_DROID_EXTRA_CARD_ARGS='+LEGACY not in sv.get('Environment','')):
            raise GuardError('Drop-in TEMPORANEO non applicato prima del riavvio')
        # Mark restart as attempted BEFORE running it. An interrupted restart
        # may have already applied temporary args and must always be undone.
        needs_restore_pulse=True
        ctl('restart',SERVICE,timeout=45)
        pid,args=wait_pulse(legacy=True,timeout=30)
        emit('legacy_attivo_temporaneo',pid=pid,args=args)
        ctl('start',UNIT_NAME,timeout=25)
        mon=props(UNIT_NAME,['ActiveState','MainPID'])
        if mon.get('ActiveState')!='active' or int(mon.get('MainPID','0'))<2:
            raise GuardError('Monitor temporaneo non avviato')
        emit('monitor_temporaneo_attivo',pid=int(mon['MainPID']))
        physical_acceptance()   # Includes explicit keep-on-reboot consent.
        # Commit the permanent config ONLY after physical tests + consent.
        create_only(LEGACY_CONF, LEGACY_TEXT.encode('utf-8'), 0o600)
        if not trial_present():
            raise GuardError('Override temporaneo scomparso inatteso')
        TRIAL.unlink()
        ctl('daemon-reload',timeout=18)
        sv=service()
        if str(LEGACY_CONF) not in sv.get('DropInPaths','').split() or str(TRIAL) in sv.get('DropInPaths','').split():
            raise GuardError('Override persistente non installato correttamente')
        if 'PULSE_MODULES_DROID_EXTRA_CARD_ARGS='+LEGACY not in sv.get('Environment',''):
            raise GuardError('Parametro legacy persistente non disponibile')
        ctl('restart',SERVICE,timeout=45)
        p2,args2=wait_pulse(legacy=True,timeout=30)
        emit('legacy_persistente_verificato',pid=p2,args=args2)
        install_link()
        ctl('daemon-reload',timeout=18)
        if ctl('is-enabled',UNIT_NAME)!='enabled':
            raise GuardError('Monitor non abilitato dopo installazione')
        verify()
        emit('installazione',ok=True,persistent=True,original_binary_unchanged=True,
             audio6_unchanged=True,session_test='TRRS+TRS+speaker auto')
    except BaseException:
        if touched:
            try:
                remove_ours(restart_audio=needs_restore_pulse)
            except BaseException as ex:
                emit('ripristino_fallito',reason=str(ex)[:180],
                     action='eseguire --ripristina (anche dal file installato); riavvio se necessario')
        raise


@contextlib.contextmanager
def lock():
    if exists(LOCK):
        st=LOCK.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=UID:
            raise GuardError('Lock utente inatteso')
    fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as ex:
            raise GuardError('Altra operazione TRRS gia in corso') from ex
        yield
    finally:
        fcntl.flock(fd,fcntl.LOCK_UN)
        os.close(fd)


def run_cli():
    parser=argparse.ArgumentParser(description='Ubuntu Touch S10+ TRRS legacy auto: prova con rollback')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--controlla',action='store_true')
    mode.add_argument('--installa',action='store_true')
    mode.add_argument('--verifica',action='store_true')
    mode.add_argument('--ripristina',action='store_true')
    mode.add_argument('--monitor',action='store_true',help=argparse.SUPPRESS)
    arg=parser.parse_args()
    if arg.monitor:
        monitor()
        return 0
    # Turn SIGTERM/HUP into unwindable exceptions: interrupted installation
    # must traverse the same finally/rollback path as Ctrl-C.
    def cancel(signum, frame):
        raise KeyboardInterrupt()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, cancel)
    emit('inizio',version=VERSION,mode='installa' if arg.installa else 'controlla' if arg.controlla else 'verifica' if arg.verifica else 'ripristina')
    with lock():
        if arg.controlla:
            state=can_configure()
            emit('controllo',ok=True,**state,modulo=PKG_VERSION,
                 module_sha=ORIGINAL_SHA,no_changes=True)
        elif arg.installa:
            install()
        elif arg.verifica:
            verify()
        else:
            assert_user()
            remove_ours(restart_audio=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(run_cli())
    except KeyboardInterrupt:
        emit('interrotto',note='se installazione era iniziata, ripristino tentato')
        sys.exit(130)
    except (GuardError,OSError,ValueError,RuntimeError) as ex:
        emit('errore',reason=str(ex)[:260])
        sys.exit(1)
