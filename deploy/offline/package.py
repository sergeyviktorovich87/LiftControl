"""Package a network-free update for an installed LiftControl server."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPORTLAB_WHEEL = 'reportlab-4.4.9-py3-none-any.whl'
REPORTLAB_SHA256 = '68e2d103ae8041a37714e8896ec9b79a1c1e911d68c3bd2ea17546568cf17bfd'
FONT_DIR = Path('/usr/share/fonts/truetype/dejavu')


def copy_tree(source, target):
    shutil.copytree(source,target,ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.sqlite3'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--commit',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--wheel-dir',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}',args.commit): raise ValueError('Use an exact source commit')
    web=ROOT/'web/dist'
    if '/static/web/assets/' not in (web/'index.html').read_text():
        raise ValueError('Build web with npm run build -- --base=/static/web/')
    version = re.search(r"^VERSION = '(\d+\.\d+\.\d+)'$", (ROOT/'backend/core/updates.py').read_text(), re.M).group(1)
    wheel = args.wheel_dir/REPORTLAB_WHEEL
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != REPORTLAB_SHA256:
        raise ValueError('Unexpected ReportLab wheel checksum')
    destination=Path(args.output).resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='liftcontrol-offline-update-') as temp:
        package=Path(temp)/f'LiftControl-v{version}-update'
        payload=package/'payload';payload.mkdir(parents=True)
        for folder in ('core','liftcontrol','templates','static'):
            copy_tree(ROOT/'backend'/folder,payload/folder)
        # Keep first-party PWA files, replace only generated Vite assets.
        shutil.rmtree(payload/'static/web/assets',ignore_errors=True)
        shutil.copytree(web/'assets',payload/'static/web/assets')
        shutil.copyfile(web/'index.html',payload/'templates/index.html')
        shutil.copyfile(ROOT/'backend/requirements.txt',payload/'requirements.txt')
        shutil.copyfile(ROOT/'deploy/api/PUBLISH-ANDROID.md',package/'PUBLISH-ANDROID.md')
        (package/'wheels').mkdir()
        shutil.copyfile(wheel,package/'wheels'/wheel.name)
        fonts=payload/'fonts'; fonts.mkdir()
        shutil.copyfile(FONT_DIR/'DejaVuSans.ttf',fonts/'DejaVuSans.ttf')
        shutil.copyfile('/usr/share/doc/fonts-dejavu-core/copyright',fonts/'DejaVu-LICENSE.txt')
        for filename in ('Dockerfile','update-panel.sh','UPDATE.md','compose.media.yaml','compose.uploads.yaml','compose.fcm-updates.yaml','compose.inspections.yaml','copy-media.py','backup-media.py'):
            shutil.copyfile(ROOT/'deploy/offline'/filename,package/filename)
        for filename in ('access.py','setup-public.sh','renew-public.sh','status-public.sh','rollback-public.sh'):
            shutil.copyfile(ROOT/'deploy/public'/filename,package/filename)
        for filename in ('configure-push.sh','compose.push.yaml','compose.updates.yaml','configure-fcm.py','compose.fcm.yaml','publish-update.py','publish-android.sh'):
            shutil.copyfile(ROOT/'deploy/api'/filename,package/filename)
        (package/'SOURCE_COMMIT.txt').write_text(args.commit+'\n')
        (package/'VERSION.txt').write_text(version+'\n')
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
