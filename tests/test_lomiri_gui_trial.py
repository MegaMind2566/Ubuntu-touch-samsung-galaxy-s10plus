"""Timed GUI trial policy/filesystem fixtures; no mount, service or phone call."""
import copy
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/lomiri-gui-trial/trial.py'
SPEC = importlib.util.spec_from_file_location('gui_trial', SCRIPT)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FileGuards(unittest.TestCase):
    def test_relative_paths_reject_escape_absolute_and_shell_text(self):
        for name in ('/etc/passwd', '../x', 'qml/../x', 'qml/x;id', 'C:/x'):
            with self.assertRaises(m.Refused): m.relative(name)
        self.assertEqual(str(m.relative('qml/Panel/Glass/GlassHome.qml')), 'qml/Panel/Glass/GlassHome.qml')

    def test_inventory_binds_file_content_and_rejects_special_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);(root/'ok.qml').write_bytes(b'Item {}\n')
            values, size = m.inventory(root)
            self.assertEqual(values, {'ok.qml':m.digest(b'Item {}\n')})
            self.assertEqual(size, 8)

    def test_inventory_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'MAX_BYTES',3):
            root=Path(tmp);(root/'x').write_bytes(b'four')
            with self.assertRaises(m.Refused):m.inventory(root)

    def test_mountinfo_decodes_spaces_and_checks_nested_mounts(self):
        text='12 1 0:1 / /usr/share/lomiri ro - tmpfs tmpfs ro\n13 1 0:1 / /safe\\040place rw - tmpfs tmpfs rw\n'
        values=m.mountpoints(text)
        self.assertIn('/safe place',values)
        with self.assertRaises(m.Refused):m.reject_live_mounts(values)
        with self.assertRaises(m.Refused):m.reject_live_mounts({m.LIVE.as_posix()+'/Panel':{}})

    def test_malformed_mountinfo_is_not_treated_as_no_mount(self):
        with self.assertRaises(m.Refused):m.mountpoints('bad mount record')

    def test_foreign_mount_is_never_unmounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            live=Path(tmp);state={'candidate_dev':-1,'candidate_ino':-1}
            with patch.object(m,'LIVE',live),patch.object(m,'mountpoints',return_value={str(live):{'id':'7'}}):
                with self.assertRaisesRegex(m.Refused,'foreign-mount'):m.own_mount(state)

    def test_changed_mount_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            live=Path(tmp);info=live.stat();state={'candidate_dev':info.st_dev,'candidate_ino':info.st_ino,'mount_id':'6'}
            with patch.object(m,'LIVE',live),patch.object(m,'mountpoints',return_value={str(live):{'id':'7'}}):
                with self.assertRaisesRegex(m.Refused,'mount-identity'):m.own_mount(state)

    def test_nested_foreign_mount_is_rejected_before_recovery(self):
        with patch.object(m,'mountpoints',return_value={m.LIVE.as_posix()+'/Panel':{'id':'8'}}):
            with self.assertRaisesRegex(m.Refused,'foreign-nested-mount'):m.own_mount({})

    def test_public_status_whitelist_has_no_private_inventory_or_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'status.json'
            state={'phase':'armed','rollback_was_armed':True,'deadline_epoch':123,
                   'original_tree':{'private/path':'hash'},'activation_unit':'private-unit',
                   'identity':{'user':'private-user'}}
            with patch.object(m,'PUBLIC_STATUS',path),patch.object(m,'safe_path',side_effect=lambda p,**k:Path(p)):
                m.publish_state(state)
            data=json.loads(path.read_text())
            self.assertEqual(data['phase'],'armed');self.assertTrue(data['rollback_was_armed'])
            for text in ('private/path','private-unit','private-user','token'):
                self.assertNotIn(text,path.read_text())
            self.assertNotIn('command',data)
            self.assertFalse(data['handset_gui_accepted'])


class TimedPolicy(unittest.TestCase):
    def setUp(self):
        self.lock=patch.object(m,'restore_lock',side_effect=contextlib.nullcontext)
        self.lock.start();self.addCleanup(self.lock.stop)
        self.records=patch.object(m,'state_write')
        self.records.start();self.addCleanup(self.records.stop)
    def fixture(self, tmp):
        run=Path(tmp)/'run';run.mkdir();(run/'stage/qml').mkdir(parents=True);(run/'rollback.py').write_bytes(b'rollback')
        return run,{'phase':'staged','manifest_sha256':'a'*64,'candidate_tree':{},'rollback_sha256':m.digest(b'rollback')}

    def execute(self, run, state, *, timer_failure=False, mount_failure=False):
        events=[];mounted=[False]
        def cmd(*args,**kwargs):
            events.append(('command',args))
            if args[:2]==('/usr/bin/mount','--bind'):
                if mount_failure:raise m.Refused('mount-failure')
                mounted[0]=True
            return 'active'
        def schedule(unit,seconds,*args):
            events.append(('timer',seconds,args))
            if timer_failure:raise m.Refused('timer-failure')
        contexts=[patch.object(m,'RUN',run),patch.object(m,'environment',return_value={}),
          patch.object(m,'load_candidate',return_value=(Path('pkg'),{},None)),patch.object(m,'inspect_live'),
          patch.object(m,'state_read',return_value=copy.deepcopy(state)),patch.object(m,'state_write'),
          patch.object(m,'inventory',return_value=({},0)),patch.object(m,'read_regular',return_value=b'rollback'),
          patch.object(m,'schedule',side_effect=schedule),patch.object(m,'command',side_effect=cmd),
          patch.object(m,'own_mount',side_effect=lambda s:mounted[0]),
          patch.object(m,'mountpoints',side_effect=lambda:{str(m.LIVE):{'id':'11','options':['ro']}} if mounted[0] else {}),
          patch.object(m,'restore',side_effect=lambda:events.append(('restore',)))]
        import contextlib
        with contextlib.ExitStack() as stack:
            for context in contexts:stack.enter_context(context)
            try:result=m.trial(Path('pkg'),'a'*64)
            except m.Refused:result=None
        return events,result

    def test_pid1_rollback_is_verified_before_bind_and_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,state=self.fixture(tmp);events,result=self.execute(run,state)
            timer=next(i for i,e in enumerate(events) if e[0]=='timer' and e[1]==600)
            mount=next(i for i,e in enumerate(events) if e[0]=='command' and e[1][:2]==('/usr/bin/mount','--bind'))
            activation=next(i for i,e in enumerate(events) if e[0]=='timer' and e[1]==3)
            self.assertLess(timer,mount);self.assertLess(mount,activation)
            self.assertFalse(result['automatic_acceptance'])

    def test_timer_failure_has_no_mount_or_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,state=self.fixture(tmp);events,result=self.execute(run,state,timer_failure=True)
            self.assertIsNone(result)
            self.assertFalse(any(e[0]=='command' for e in events))

    def test_mount_failure_attempts_immediate_restore_without_cancelling_timer(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,state=self.fixture(tmp);events,result=self.execute(run,state,mount_failure=True)
            self.assertIsNone(result);self.assertIn(('restore',),events)
            self.assertFalse(any('stop' in e[1] for e in events if e[0]=='command'))

    def test_changed_private_candidate_does_not_arm_timer(self):
        with tempfile.TemporaryDirectory() as tmp:
            run,state=self.fixture(tmp);state['candidate_tree']={'tampered':'x'}
            with self.assertRaisesRegex(m.Refused,'private-stage'):
                with patch.object(m,'RUN',run),patch.object(m,'environment'),patch.object(m,'load_candidate',return_value=(None,{},None)),patch.object(m,'inspect_live'),patch.object(m,'state_read',return_value=state),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'schedule') as schedule:
                    m.trial(Path('pkg'),'a'*64)
            schedule.assert_not_called()

    def test_restore_can_run_with_failed_lightdm_and_checks_original_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'phase':'mounted','original_tree':{'original':'sha'}};events=[]
            def cmd(*args,**kwargs):events.append(args);return 'active'
            with patch.object(m,'RUN',Path(tmp)),patch.object(m,'environment') as environment,patch.object(m,'state_read',return_value=state),patch.object(m,'state_write'),patch.object(m,'own_mount',return_value=True),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({'original':'sha'},0)),patch.object(m,'command',side_effect=cmd):
                result=m.restore()
            environment.assert_called_once_with(require_lightdm=False)
            stop=events.index(('/usr/bin/systemctl','stop','lightdm.service'))
            unmount=events.index(('/usr/bin/umount',str(m.LIVE)))
            start=events.index(('/usr/bin/systemctl','start','lightdm.service'))
            self.assertLess(stop,unmount);self.assertLess(unmount,start)
            self.assertTrue(result['visual_recovery_pending'])

    def test_restore_mismatch_is_failure_but_attempts_display_recovery(self):
        state={'phase':'mounted','original_tree':{'original':'sha'}}
        with patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=False),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'command',return_value='active') as command:
            with self.assertRaisesRegex(m.Refused,'original-hash'):m.restore()
            self.assertIn(('/usr/bin/systemctl','start','lightdm.service'),[c.args for c in command.call_args_list])
            self.assertEqual(state['phase'],'restore-failed')

    def test_restore_is_idempotent_after_verified_early_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);(run/'ROLLBACK_OK').write_text('ORIGINAL_HASHES_AND_LIGHTDM_ACTIVE\n')
            state={'phase':'restored','original_tree':{}}
            with patch.object(m,'RUN',run),patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=False),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'read_regular',return_value=b'confirmed'),patch.object(m,'command',return_value='active') as command:
                result=m.restore()
            self.assertEqual(result['rollback'],'already-confirmed')
            self.assertFalse(any('restart' in call.args for call in command.call_args_list))

    def test_inactive_rc3_does_not_block_real_command_adapter_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'phase':'mounted','original_tree':{}};calls=[];started=[False]
            def run(argv,**kwargs):
                calls.append(argv)
                if 'is-active' in argv:return subprocess.CompletedProcess(argv,3,b'inactive\n',b'')
                if tuple(argv[1:])==('start','lightdm.service'):started[0]=True
                out=b'active\n' if started[0] else b'inactive\n'
                return subprocess.CompletedProcess(argv,0,out,b'')
            with patch.object(m,'RUN',Path(tmp)),patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=False),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m.subprocess,'run',side_effect=run):
                m.restore()
            self.assertTrue(started[0]);self.assertFalse(any('is-active' in call for call in calls))

    def test_both_owned_activation_units_are_stopped_before_display(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'phase':'mounted','original_tree':{},'activation_unit':'ut-s10-gui-12-123-activate'};calls=[]
            def cmd(*args,**kwargs):calls.append(args);return 'loaded' if 'LoadState' in args else 'active'
            with patch.object(m,'RUN',Path(tmp)),patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=False),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'command',side_effect=cmd):m.restore()
            display=calls.index(('/usr/bin/systemctl','stop','lightdm.service'))
            for suffix in ('.timer','.service'):
                self.assertLess(calls.index(('/usr/bin/systemctl','stop',state['activation_unit']+suffix)),display)

    def test_unmount_error_still_starts_display_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            state={'phase':'mounted','original_tree':{}};calls=[]
            def cmd(*args,**kwargs):
                calls.append(args)
                if args[0]=='/usr/bin/umount':raise m.Refused('busy')
                return 'active'
            with patch.object(m,'RUN',Path(tmp)),patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=True),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'command',side_effect=cmd):
                with self.assertRaisesRegex(m.Refused,'owned-unmount'):m.restore()
            self.assertIn(('/usr/bin/systemctl','start','lightdm.service'),calls)
            self.assertFalse(state['rollback_commands_verified'])

    def test_status_write_error_cannot_prevent_display_recovery(self):
        state={'phase':'mounted','original_tree':{}};calls=[]
        with patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',return_value=False),patch.object(m,'mountpoints',return_value={}),patch.object(m,'inventory',return_value=({},0)),patch.object(m,'state_write',side_effect=OSError('full')),patch.object(m,'command',side_effect=lambda *a,**k:calls.append(a) or 'active'):
            with self.assertRaisesRegex(m.Refused,'recovery-record'):m.restore()
        self.assertIn(('/usr/bin/systemctl','start','lightdm.service'),calls)

    def test_foreign_mount_never_stops_unrelated_display(self):
        state={'phase':'mounted','original_tree':{}}
        with patch.object(m,'environment'),patch.object(m,'state_read',return_value=state),patch.object(m,'own_mount',side_effect=m.Refused('foreign-mount')),patch.object(m,'command') as command:
            with self.assertRaisesRegex(m.Refused,'foreign-mount'):m.restore()
        command.assert_not_called()


if __name__=='__main__':unittest.main()
