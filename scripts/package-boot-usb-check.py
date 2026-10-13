"""Produce a host-only Windows USB collector, without handset dependencies."""
import argparse
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-controllo-USB-avvio-Windows.zip')
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for source,destination in (
            ('scripts/check-boot-usb.ps1','scripts/check-boot-usb.ps1'),
            ('tools/windows/CONTROLLA-USB-AVVIO.cmd','CONTROLLA-USB-AVVIO.cmd'),
            ('tools/windows/LEGGIMI-USB-AVVIO.txt','LEGGIMI-USB-AVVIO.txt'),
        ):
            content=(ROOT/source).read_text().replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
            archive.writestr(destination,content)
    print(args.output)


if __name__=='__main__':main()
