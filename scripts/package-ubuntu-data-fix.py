"""Small replacement script for an already prepared Ubuntu installation."""
import argparse
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'out/UbuntuTouch-S10plus-correzione-dati-Windows.zip')
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for source,destination in [('scripts/install-ubuntu-touch.ps1','scripts/install-ubuntu-touch.ps1'),
                                   ('tools/windows/LEGGIMI-CORREZIONE-DATI.txt','LEGGIMI-CORREZIONE-DATI.txt')]:
            content=(ROOT/source).read_text().replace('\r\n','\n').replace('\n','\r\n').encode('ascii')
            archive.writestr(destination,content)
    print(f'{args.output}: {args.output.stat().st_size} bytes')


if __name__=='__main__':main()
