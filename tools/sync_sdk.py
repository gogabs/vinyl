"""Refresh the bundled Mage Core fallback from a clean Mage Core Git checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,default=ROOT.parent/'r36s-a11y-sdk')
    args=parser.parse_args()
    source=args.sdk.resolve()
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain']).strip():
        raise SystemExit('Mage Core checkout has local changes; commit or select a clean checkout')
    commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD']).decode().strip()
    package=source/'python/r36s_a11y'
    if not (package/'graphics.py').is_file(): raise SystemExit('Mage Core graphics API is missing')
    target=ROOT/'r36s_a11y'
    files=[p for p in package.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    hashes={}
    for file in files:
        relative=file.relative_to(package)
        destination=target/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        data=file.read_bytes()
        if file.suffix=='.py': data=data.replace(b'\r\n',b'\n')
        destination.write_bytes(data)
        hashes[relative.as_posix()]=hashlib.sha256(data).hexdigest()
    # Remove obsolete Python sources only inside this repository's fallback.
    for file in target.rglob('*.py'):
        if file.relative_to(target).as_posix() not in hashes:
            file.unlink()
    (ROOT/'sdk-origin.json').write_text(json.dumps({'repository':'gogabs/r36s-a11y-sdk','commit':commit,'sha256':hashes},indent=2)+'\n',encoding='utf8')
    print('Mage Core fallback synchronized at '+commit)


if __name__=='__main__': main()
