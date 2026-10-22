import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/ut-s10-trrs-integrato.py'
spec=importlib.util.spec_from_file_location('trrs_int_safe_v3',SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class StateTests(unittest.TestCase):
    def test_switch_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=Path(tmp)/'jack'
            j.write_text('MECHANICAL=0\nMICROPHONE=0\nHEADPHONE=0\n')
            with mock.patch.object(mod,'JACK',j):
                self.assertEqual(mod.jack_state(),'none')
    def test_switch_trrs_mic_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=Path(tmp)/'jack'
            j.write_text('MECHANICAL=1\nMICROPHONE=1\nHEADPHONE=0\n')
            with mock.patch.object(mod,'JACK',j):
                self.assertEqual(mod.jack_state(),'trrs')
    def test_switch_trs_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=Path(tmp)/'jack'
            j.write_text('MECHANICAL=1\nMICROPHONE=0\nHEADPHONE=1\n')
            with mock.patch.object(mod,'JACK',j):
                self.assertEqual(mod.jack_state(),'trs')
    def test_ambiguous_switch_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            j=Path(tmp)/'jack'
            j.write_text('MECHANICAL=0\nMICROPHONE=1\nHEADPHONE=0\n')
            with mock.patch.object(mod,'JACK',j):
                self.assertEqual(mod.jack_state(),'unknown')
    def test_trrs_triggers_headset(self):
        self.assertEqual(mod.monitor_routing('trrs',mod.SPEAKER,mod.SINK,True),mod.HEADSET)
    def test_trrs_already_headset_does_nothing(self):
        self.assertIsNone(mod.monitor_routing('trrs',mod.HEADSET,mod.SINK,True))
    def test_removal_returns_speaker(self):
        self.assertEqual(mod.monitor_routing('none',mod.HEADSET,mod.SINK,True),mod.SPEAKER)
    def test_removal_leaves_already_speaker(self):
        self.assertIsNone(mod.monitor_routing('none',mod.SPEAKER,mod.SINK,True))
    def test_does_not_change_trs(self):
        for cur in (mod.SPEAKER,mod.HEADSET,mod.HEADPHONES):
            self.assertIsNone(mod.monitor_routing('trs',cur,mod.SINK,True))
    def test_does_not_change_bluetooth_default(self):
        for kind in ('trrs','none','trs'):
            self.assertIsNone(mod.monitor_routing(kind,mod.SPEAKER,'bluez_output.test',True))
    def test_does_not_route_without_legacy(self):
        self.assertIsNone(mod.monitor_routing('trrs',mod.SPEAKER,mod.SINK,False))
    def test_paused_stream_allowed(self):
        with mock.patch.object(mod,'js_pulse',return_value=[{'corked':True}]):
            self.assertEqual(mod.paused_streams(),1)
    def test_active_stream_blocked(self):
        with mock.patch.object(mod,'js_pulse',return_value=[{'corked':False}]):
            with self.assertRaisesRegex(mod.GuardError,'Riproduzione audio attiva'):
                mod.paused_streams()
    def test_unknown_stream_blocked(self):
        with mock.patch.object(mod,'js_pulse',return_value=[{'corked':None}]):
            with self.assertRaisesRegex(mod.GuardError,'ambiguo'):
                mod.paused_streams()
    def test_port_decode_dict_or_name(self):
        self.assertEqual(mod.port_name({'name':mod.HEADSET}),mod.HEADSET)
        self.assertEqual(mod.port_name(mod.SPEAKER),mod.SPEAKER)
    def test_tone_volume_and_duration(self):
        raw=mod.tone()
        self.assertEqual(len(raw),153600)
        import struct
        self.assertLess(max(abs(v) for v in struct.unpack('<76800h',raw)),1500)
    def test_source_scripts_syntactically_valid(self):
        compile(SCRIPT.read_text(),str(SCRIPT),'exec')


ORIGINAL_VERIFY=mod.verify
ORIGINAL_CAN_CONFIGURE=mod.can_configure
ORIGINAL_PHYSICAL_ACCEPTANCE=mod.physical_acceptance

class SimulatedPhone(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.home=self.root/'home'/'phablet'; self.home.mkdir(parents=True)
        self.runtime=self.root/'run'/'user'/'32011';self.runtime.mkdir(parents=True)
        (self.runtime/'bus').touch()
        self.jack=self.root/'extcon1';self.jack.write_text('MECHANICAL=0\nMICROPHONE=0\nHEADPHONE=0\n')
        self.audio6=self.home/'.config/systemd/user/pulseaudio.service.d/91-ut-s10-audio6.conf'
        self.audio6.parent.mkdir(parents=True)
        self.audio6.write_bytes(b'proven-audio6-v2')
        self.original=self.root/'module-droid-card-30.so';self.original.write_bytes(b'original-arm64-driver')
        self.legacyconf=self.home/'.config/systemd/user/pulseaudio.service.d/93-ut-s10-trrs-legacy.conf'
        self.unitfile=self.home/'.config/systemd/user/ut-s10-trrs-autoswitch.service'
        self.scriptfile=self.home/'.local/libexec/ut-s10-trrs-integrato.py'
        self.unitlink=self.home/'.config/systemd/user/default.target.wants/ut-s10-trrs-autoswitch.service'
        self.trial=self.runtime/'systemd/user/pulseaudio.service.d/94-ut-s10-trrs-integration-trial.conf'
        self.older=self.runtime/'systemd/user/pulseaudio.service.d/92-ut-s10-trrs-legacy-trial.conf'
        self.lock=self.runtime/'ut-s10-trrs-integration.lock'
        self.args=mod.BASE_ARGS;self.pid=5851;self.monitor_active=False
        self.port=mod.SPEAKER;self.default_sink=mod.SINK;self.default_source=mod.SOURCE
        self.audio_restarts=0;self.accept_calls=0;self.confirmed=False
        self.patchers=[]
        replacements={
            'UID':os.getuid(), 'HOME':self.home,'RUNTIME':self.runtime,'JACK':self.jack,
            'AUDIO6':self.audio6,'AUDIO6_SHA':hashlib.sha256(self.audio6.read_bytes()).hexdigest(),
            'ORIGINAL':self.original,'ORIGINAL_SHA':hashlib.sha256(self.original.read_bytes()).hexdigest(),
            'LEGACY_CONF':self.legacyconf,'UNIT_FILE':self.unitfile,'SCRIPT_FILE':self.scriptfile,
            'UNIT_LINK':self.unitlink,'TRIAL':self.trial,'OLDER_TRIAL':self.older,'LOCK':self.lock,
        }
        for name,value in replacements.items():
            p=mock.patch.object(mod,name,value);p.start();self.addCleanup(p.stop)
        for name,val in {'ctl':self.ctl,'service':self.service,'module_args':self.module_args,
            'pulse':self.pulse,'sink_port':self.sink_port,'wait_pulse':self.wait_pulse,'props':self.props,
            'physical_acceptance':self.physical_acceptance,'verify':self.verify,
            'can_configure':self.can_configure}.items():
            p=mock.patch.object(mod,name,side_effect=val)
            p.start();self.addCleanup(p.stop)
        p=mock.patch.object(mod,'emit');p.start();self.addCleanup(p.stop)
        p=mock.patch.object(Path,'home',return_value=self.home);p.start();self.addCleanup(p.stop)
        p=mock.patch.object(mod.os,'getgid',return_value=os.getuid());p.start();self.addCleanup(p.stop)
    def ctl(self,*args,**kwargs):
        if args[0]=='show' and args[1]==mod.UNIT_NAME:
            return 'ActiveState='+('active' if self.monitor_active else 'inactive')
        if args[0]=='restart':
            self.audio_restarts+=1
            self.pid+=7
            self.args=mod.BASE_ARGS+(' '+mod.LEGACY if (self.trial.exists() or self.legacyconf.exists()) else '')
            self.port=mod.SPEAKER
            return ''
        if args[0]=='start' and args[1]==mod.UNIT_NAME:
            self.monitor_active=True
        if args[0]=='stop' and args[1]==mod.UNIT_NAME:
            self.monitor_active=False
        if args[0]=='is-enabled':
            return 'enabled' if self.unitlink.exists() else 'disabled'
        return ''
    def service(self):
        paths=[str(self.audio6)]
        if self.trial.exists():paths.append(str(self.trial))
        if self.legacyconf.exists():paths.append(str(self.legacyconf))
        return {'DropInPaths':' '.join(paths),'Environment':('PULSE_MODULES_DROID_EXTRA_CARD_ARGS='+mod.LEGACY) if (self.trial.exists() or self.legacyconf.exists()) else '', 'MainPID':str(self.pid)}
    def props(self,name,names):
        if name==mod.UNIT_NAME:return {'ActiveState':'active' if self.monitor_active else 'inactive', 'MainPID':'1011' if self.monitor_active else '0'}
        if name==mod.SERVICE:return self.service()
        return {}
    def module_args(self):return self.args
    def pulse(self,*args):
        if args==('get-default-sink',):return self.default_sink
        if args==('get-default-source',):return self.default_source
        if args and args[0]=='set-sink-port':
            self.port=args[2]
            return ''
        raise AssertionError(args)
    def sink_port(self):return self.port
    def wait_pulse(self,legacy,timeout=30):
        has=mod.LEGACY in self.args.split()
        if has != legacy:raise mod.GuardError('Wrong legacy mode')
        self.assertEqual(self.port,mod.SPEAKER)
        return self.pid,self.args
    def physical_acceptance(self):
        self.accept_calls+=1
        self.assertTrue(self.trial.exists(),'Trial in /run must be present until physical consent')
        self.assertFalse(self.legacyconf.exists(),'Persistent file MUST NOT exist prior to acceptance')
        self.assertTrue(self.monitor_active)
        self.assertIn(mod.LEGACY,self.args)
        if not self.confirmed:
            raise mod.GuardError('User did not confirm physical test')
    def verify(self):
        self.assertTrue(self.legacyconf.exists())
        self.assertFalse(self.trial.exists())
        self.assertTrue(self.unitlink.is_symlink())
        self.assertTrue(self.monitor_active)
        self.assertIn(mod.LEGACY,self.args)
    def can_configure(self):return {'pid':self.pid,'paused':1,'jack':'none'}
    def _install(self,confirm=True,first_confirm='s'):
        self.confirmed=confirm
        with mock.patch.object(mod,'prompt',return_value=first_confirm):
            return mod.install()

    def test_actual_preflight_accepts_corked_maliit_stream(self):
        with mock.patch.object(mod,'baseline'), \
             mock.patch.object(mod,'sink_ports',return_value={mod.SPEAKER,mod.HEADSET,mod.HEADPHONES}), \
             mock.patch.object(mod,'paused_streams',return_value=1):
            result=ORIGINAL_CAN_CONFIGURE()
        self.assertEqual(result['paused'],1)
        self.assertEqual(result['pid'],self.pid)

    def test_actual_preflight_rejects_other_audio_module_args(self):
        self.args='voice_virtual_stream=true changed=1'
        with mock.patch.object(mod,'baseline'), \
             mock.patch.object(mod,'sink_ports',return_value={mod.SPEAKER,mod.HEADSET,mod.HEADPHONES}), \
             mock.patch.object(mod,'paused_streams',return_value=1):
            with self.assertRaisesRegex(mod.GuardError,'argomenti iniziali diversi'):
                ORIGINAL_CAN_CONFIGURE()

    def test_actual_preflight_refuses_existing_temporary_trial(self):
        mod.create_trial()
        with mock.patch.object(mod,'baseline'):
            with self.assertRaisesRegex(mod.GuardError,'Override di prova'):
                ORIGINAL_CAN_CONFIGURE()

    def test_actual_preflight_refuses_previous_trial(self):
        self.older.parent.mkdir(parents=True)
        self.older.write_text('old trial')
        with mock.patch.object(mod,'baseline'):
            with self.assertRaisesRegex(mod.GuardError,'Override di prova'):
                ORIGINAL_CAN_CONFIGURE()

    def test_real_verify_after_install(self):
        self._install(confirm=True)
        with mock.patch.object(mod,'baseline'):
            ORIGINAL_VERIFY()

    def test_no_restart_before_explicit_first_consent(self):
        self._install(first_confirm='')
        self.assertEqual(self.audio_restarts,0)

    def test_monitor_loop_routes_headset_after_stable_insert(self):
        mod.create_files()
        mod.create_trial()
        def jack_state():return 'trrs'
        self.args=mod.BASE_ARGS+' '+mod.LEGACY
        count=[0]
        def pause(_):
            count[0]+=1
            if count[0]>=3:raise KeyboardInterrupt
        with mock.patch.object(mod,'assert_user'), \
             mock.patch.object(mod,'jack_state',side_effect=jack_state), \
             mock.patch.object(mod,'pa_pid',return_value=self.pid), \
             mock.patch.object(mod.time,'sleep',side_effect=pause):
            with self.assertRaises(KeyboardInterrupt):mod.monitor()
        self.assertEqual(self.port,mod.HEADSET)

    def test_monitor_loop_reverts_headset_on_unplug(self):
        mod.create_files()
        mod.create_trial()
        self.args=mod.BASE_ARGS+' '+mod.LEGACY
        self.port=mod.HEADSET
        count=[0]
        def pause(_):
            count[0]+=1
            if count[0]>=3:raise KeyboardInterrupt
        with mock.patch.object(mod,'assert_user'), \
             mock.patch.object(mod,'jack_state',return_value='none'), \
             mock.patch.object(mod,'pa_pid',return_value=self.pid), \
             mock.patch.object(mod.time,'sleep',side_effect=pause):
            with self.assertRaises(KeyboardInterrupt):mod.monitor()
        self.assertEqual(self.port,mod.SPEAKER)

    def test_monitor_loop_does_not_touch_trs(self):
        mod.create_files()
        mod.create_trial()
        self.args=mod.BASE_ARGS+' '+mod.LEGACY
        self.port=mod.HEADPHONES
        count=[0]
        def pause(_):
            count[0]+=1
            if count[0]>=3:raise KeyboardInterrupt
        with mock.patch.object(mod,'assert_user'), \
             mock.patch.object(mod,'jack_state',return_value='trs'), \
             mock.patch.object(mod,'pa_pid',return_value=self.pid), \
             mock.patch.object(mod.time,'sleep',side_effect=pause):
            with self.assertRaises(KeyboardInterrupt):mod.monitor()
        self.assertEqual(self.port,mod.HEADPHONES)

    def test_monitor_loop_preserves_bluetooth_default(self):
        mod.create_files()
        mod.create_trial()
        self.args=mod.BASE_ARGS+' '+mod.LEGACY
        self.default_sink='bluez_output.test'
        count=[0]
        def pause(_):
            count[0]+=1
            if count[0]>=3:raise KeyboardInterrupt
        with mock.patch.object(mod,'assert_user'), \
             mock.patch.object(mod,'jack_state',return_value='trrs'), \
             mock.patch.object(mod,'pa_pid',return_value=self.pid), \
             mock.patch.object(mod.time,'sleep',side_effect=pause):
            with self.assertRaises(KeyboardInterrupt):mod.monitor()
        self.assertEqual(self.port,mod.SPEAKER)

    def test_actual_physical_acceptance_three_outputs(self):
        self._install(confirm=True)
        idx=[0]
        responses=['','', 'c','', '', 's', '', 's', 's']
        pairs=[None,'trrs',None,'none','trs',None,'none',None,None]
        def interactive(msg,timeout=90):
            i=idx[0];idx[0]+=1
            if i>=len(responses):raise AssertionError('Unexpected prompt '+msg)
            state=pairs[i]
            if state=='trrs':
                self.jack.write_text('MECHANICAL=1\nMICROPHONE=1\nHEADPHONE=0\n');self.port=mod.HEADSET
            elif state=='trs':
                self.jack.write_text('MECHANICAL=1\nMICROPHONE=0\nHEADPHONE=1\n');self.port=mod.HEADPHONES
            elif state=='none':
                self.jack.write_text('MECHANICAL=0\nMICROPHONE=0\nHEADPHONE=0\n');self.port=mod.SPEAKER
            return responses[i]
        with mock.patch.object(mod,'prompt',side_effect=interactive), \
             mock.patch.object(mod,'play_tone') as play, \
             mock.patch.object(mod,'paused_streams',return_value=1):
            ORIGINAL_PHYSICAL_ACCEPTANCE()
        self.assertEqual(idx[0],9)
        self.assertEqual(play.call_count,3)

    def test_unmodified_audio_binary_protected(self):
        self.original.write_bytes(b'some other binary')
        with mock.patch.object(mod,'assert_user'),mock.patch.object(mod,'output',return_value=mod.PKG_VERSION):
            with self.assertRaisesRegex(mod.GuardError,'Modulo audio ARM64 differente'):
                mod.baseline()

    def test_recovery_of_staged_trial_after_interruption(self):
        mod.create_files()
        mod.create_trial()
        self.args=mod.BASE_ARGS+' '+mod.LEGACY
        mod.remove_ours(restart_audio=True)
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertEqual(self.args,mod.BASE_ARGS)
        self.assertEqual(self.audio_restarts,1)

    def test_install_cancel_preflight_no_writes(self):
        self._install(first_confirm='n')
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertEqual(self.audio_restarts,0)
    def test_trial_declined_leaves_no_persistent_settings(self):
        with self.assertRaisesRegex(mod.GuardError,'User did not confirm'):
            self._install(confirm=False)
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.unitfile.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertFalse(self.unitlink.exists())
        self.assertFalse(self.monitor_active)
        self.assertEqual(self.args,mod.BASE_ARGS)
        self.assertEqual(self.audio_restarts,2)
    def test_install_success_commits_after_accept(self):
        self._install(confirm=True)
        self.assertEqual(self.accept_calls,1)
        self.assertEqual(self.audio_restarts,2)
        self.assertTrue(self.legacyconf.is_file())
        self.assertTrue(self.unitfile.is_file())
        self.assertTrue(self.unitlink.is_symlink())
        self.assertFalse(self.trial.exists())
        self.assertEqual(self.args,mod.BASE_ARGS+' '+mod.LEGACY)
        self.assertTrue(self.monitor_active)
    def test_clean_uninstall_restores_original_args(self):
        self._install(confirm=True)
        mod.remove_ours()
        self.assertEqual(self.audio_restarts,3)
        self.assertFalse(self.unitlink.exists())
        self.assertFalse(self.unitfile.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertEqual(self.args,mod.BASE_ARGS)
        self.assertFalse(self.monitor_active)
    def test_uninstall_idempotent_no_audio_restart(self):
        mod.remove_ours()
        self.assertEqual(self.audio_restarts,0)
    def test_partially_staged_uninstall_does_not_restart(self):
        mod.create_files()
        mod.remove_ours()
        self.assertEqual(self.audio_restarts,0)
        self.assertFalse(self.unitfile.exists())
        self.assertFalse(self.scriptfile.exists())
    def test_trial_symlink_blocked(self):
        self.trial.parent.mkdir(parents=True)
        self.trial.symlink_to(self.jack)
        with self.assertRaisesRegex(mod.GuardError,'File non previsto'):
            mod.trial_present()
    def test_trial_file_mode_private(self):
        mod.create_trial()
        self.assertEqual(stat.S_IMODE(self.trial.stat().st_mode),0o600)
        self.assertFalse(self.legacyconf.exists())
    def test_runtime_directory_symlink_blocked(self):
        path=self.runtime/'systemd'
        path.symlink_to(self.root)
        with self.assertRaisesRegex(mod.GuardError,'Directory runtime inattesa'):
            mod.create_trial()
    def test_no_override_remaining_after_rollback(self):
        mod.create_files();mod.create_trial()
        self.assertTrue(self.trial.exists())
        mod.remove_ours(restart_audio=False)
        self.assertFalse(self.trial.exists())
        self.assertEqual(self.audio_restarts,0)
    def test_if_restart_fails_rollback_is_attempted(self):
        original_ctl=self.ctl
        calls=[0]
        def failing_ctl(*args,**kw):
            if args[0]=='restart':
                calls[0]+=1
                if calls[0]==1:raise mod.GuardError('systemctl restart failed')
            return original_ctl(*args,**kw)
        with mock.patch.object(mod,'ctl',side_effect=failing_ctl):
            with self.assertRaisesRegex(mod.GuardError,'systemctl restart failed'):
                self._install(confirm=True)
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertEqual(calls[0],2)
    def test_ctrl_c_during_physical_acceptance_rolls_back(self):
        with mock.patch.object(mod,'physical_acceptance',side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):self._install(confirm=True)
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.unitlink.exists())
        self.assertEqual(self.args,mod.BASE_ARGS)
        self.assertEqual(self.audio_restarts,2)

    def test_persistent_config_creation_failure_rolls_back(self):
        original_create=mod.create_only
        def no_space(path,*args,**kw):
            if path==self.legacyconf:raise mod.GuardError('Storage full at commit')
            return original_create(path,*args,**kw)
        with mock.patch.object(mod,'create_only',side_effect=no_space):
            with self.assertRaisesRegex(mod.GuardError,'Storage full at commit'):
                self._install(confirm=True)
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.scriptfile.exists())
        self.assertEqual(self.args,mod.BASE_ARGS)

    def test_post_acceptance_permanent_restart_failure_rolls_back(self):
        original_ctl=self.ctl
        calls=[0]
        def ctl_fail_final_restart(*args,**kw):
            if args[0]=='restart':
                calls[0]+=1
                if calls[0]==2:raise mod.GuardError('Final restart failed')
            return original_ctl(*args,**kw)
        with mock.patch.object(mod,'ctl',side_effect=ctl_fail_final_restart):
            with self.assertRaisesRegex(mod.GuardError,'Final restart failed'):
                self._install(confirm=True)
        self.assertEqual(calls[0],3)
        self.assertFalse(self.trial.exists())
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.unitlink.exists())
        self.assertEqual(self.args,mod.BASE_ARGS)

    def test_staged_partial_unit_unloaded_can_be_recovered(self):
        mod.create_files()
        original_ctl=self.ctl
        def never_loaded(*args,**kw):
            if args[0]=='stop':return ''
            if args[0]=='show':return ''
            return original_ctl(*args,**kw)
        with mock.patch.object(mod,'ctl',side_effect=never_loaded):
            mod.remove_ours(restart_audio=False)
        self.assertFalse(self.unitfile.exists())
        self.assertFalse(self.scriptfile.exists())

    def test_tampered_unit_never_deleted(self):
        mod.create_files()
        self.unitfile.write_text('UNEXPECTED USER CONFIGURATION')
        with self.assertRaisesRegex(mod.GuardError,'modificato rispetto al pacchetto'):
            mod.remove_ours()
        self.assertTrue(self.unitfile.exists())

    def test_permanent_audio_conf_is_mode_600(self):
        self._install(confirm=True)
        self.assertEqual(stat.S_IMODE(self.legacyconf.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE(self.unitfile.stat().st_mode),0o600)
        self.assertEqual(stat.S_IMODE(self.scriptfile.stat().st_mode),0o600)

    def test_paths_state_refuses_nonowned_symlink_unit(self):
        self.unitfile.symlink_to(self.audio6)
        with self.assertRaisesRegex(mod.GuardError,'File non previsto'):
            mod.paths_state()

    def test_runtime_trial_removed_by_emergency_reboot_model(self):
        mod.create_files()
        mod.create_trial()
        # /run/user is volatile across reboot, the config must disappear,
        # and staged service is unenabled, so reboot preserves audio baseline.
        self.trial.unlink()
        self.assertFalse(self.legacyconf.exists())
        self.assertFalse(self.unitlink.exists())
        self.assertEqual(self.audio_restarts,0)
        mod.remove_ours(restart_audio=False)
        self.assertFalse(self.scriptfile.exists())

    def test_monitor_fails_closed_if_no_trial_or_persistent(self):
        mod.create_files()
        with self.assertRaisesRegex(mod.GuardError,'Nessuna configurazione legacy'):
            mod.monitor()


if __name__=='__main__':
    unittest.main(verbosity=2)
