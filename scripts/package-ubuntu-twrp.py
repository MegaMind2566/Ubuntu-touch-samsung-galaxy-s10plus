"""Small TWRP installer add-on; existing pinned tools/images are reused."""
import argparse
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-installa-da-TWRP-Windows.zip')
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        sources=[('scripts/install-ubuntu-twrp.ps1','scripts/install-ubuntu-twrp.ps1'),
                 ('scripts/install-ubuntu-touch.ps1','scripts/install-ubuntu-touch.ps1'),
                 ('tools/windows/INSTALLA-UBUNTU-TWRP.cmd','INSTALLA-UBUNTU-TWRP.cmd'),
                 ('tools/windows/LEGGIMI-UBUNTU-TWRP.txt','LEGGIMI-UBUNTU-TWRP.txt')]
        for source,destination in sources:
            content=(ROOT/source).read_text().replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
            archive.writestr(destination,content)
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__=='__main__':main()
