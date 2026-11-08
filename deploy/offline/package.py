"""Package a source-only, network-free update for an installed LiftControl 0.8."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def copy_tree(source, target):
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.sqlite3'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.commit): raise ValueError('Use an exact source commit')
    web=ROOT/'web/dist'
    if '/static/web/assets/' not in (web/'index.html').read_text():
        raise ValueError('Build web with npm run build -- --base=/static/web/')
    destination=Path(args.output).resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='liftcontrol-offline-update-') as temp:
        package=Path(temp)/'LiftControl-v0.9-update'
        payload=package/'payload';payload.mkdir(parents=True)
        for folder in ('core','liftcontrol','templates','static'):
            copy_tree(ROOT/'backend'/folder,payload/folder)
        shutil.rmtree(payload/'static/web',ignore_errors=True)
        (payload/'static/web').mkdir(parents=True)
        shutil.copytree(web/'assets',payload/'static/web/assets')
        shutil.copyfile(ROOT/'backend/static/web/service-worker.js',payload/'static/web/service-worker.js')
        shutil.copyfile(web/'index.html',payload/'templates/index.html')
        shutil.copyfile(ROOT/'backend/requirements.txt',payload/'requirements.txt')
        for filename in ('Dockerfile','update-panel.sh','UPDATE.md'):
            shutil.copyfile(ROOT/'deploy/offline'/filename,package/filename)
        for filename in ('access.py','setup-public.sh','renew-public.sh','status-public.sh','rollback-public.sh'):
            shutil.copyfile(ROOT/'deploy/public'/filename,package/filename)
        for filename in ('configure-push.sh','compose.push.yaml'):
            shutil.copyfile(ROOT/'deploy/api'/filename,package/filename)
        (package/'SOURCE_COMMIT.txt').write_text(args.commit+'\n')
        files=sorted(path for path in package.rglob('*') if path.is_file())
        manifest=''.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.relative_to(package).as_posix()+'\n' for path in files)
        (package/'PATCH.sha256').write_text(manifest)
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
            for path in sorted(package.rglob('*')):
                if not path.is_file(): continue
                info=zipfile.ZipInfo(path.relative_to(package.parent).as_posix(),date_time=(2026,11,8,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=(0o100755 if path.suffix=='.sh' else 0o100644)<<16
                archive.writestr(info,path.read_bytes())
    print(destination.name+' '+str(destination.stat().st_size)+' bytes')


if __name__=='__main__': main()
