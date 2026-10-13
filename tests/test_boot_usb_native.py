"""Run the actual host-only CMD on Windows, without any attached handset."""
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile


def main():
    root=Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='boot USB native ') as temp:
        folder=Path(temp)/'USB check with spaces'
        with zipfile.ZipFile(root/'out/UbuntuTouch-S10plus-controllo-USB-avvio-Windows.zip') as archive:
            archive.extractall(folder)
        result=subprocess.run(['cmd.exe','/d','/c',str(folder/'CONTROLLA-USB-AVVIO.cmd')],
                              input='\n',capture_output=True,text=True,timeout=90)
        assert result.returncode==0,result.stdout+result.stderr
        with zipfile.ZipFile(folder/'ubuntu-boot-usb-report.zip') as archive:
            report=json.loads(archive.read('boot-usb-report.json'))
        assert report['success']
        assert len(report['snapshots'])==3
        assert any(not s['errors'] for s in report['snapshots']),report
        assert not report['phone_commands_requested']
        assert not report['driver_changes_requested']
        assert not report['network_changes_requested']
        assert not report['ubuntu_touch_boot_verified']
        print('Actual PowerShell 5.1/PnP/CIM/CMD with spaces, no handset: passed')


if __name__=='__main__':main()
