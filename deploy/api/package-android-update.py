#!/usr/bin/env python3
"""Wrap a verified CI Android release in a one-command server publication kit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parent


def package(source, output):
    files={}
    with zipfile.ZipFile(source) as archive:
        info=archive.getinfo('android-release.json')
        if info.file_size>65536: raise ValueError('Описание сборки слишком большое.')
        metadata=archive.read(info)
        release=json.loads(metadata)['android']
        name=release['filename']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,150}',name) or '..' in name:
            raise ValueError('Небезопасное имя APK.')
        if archive.namelist().count(name)!=1 or archive.namelist().count('android-release.json')!=1:
            raise ValueError('Неоднозначное содержимое сборки.')
        info=archive.getinfo(name)
        if not 0<info.file_size<=200*1024*1024 or info.file_size!=release['size']:
            raise ValueError('Размер APK не совпал с описанием.')
        apk=archive.read(info)
        if hashlib.sha256(apk).hexdigest()!=release['sha256']:
            raise ValueError('Контрольная сумма APK не совпала с описанием.')
        files[name]=apk
        files['android-release.json']=metadata
        for name in ('SIGNATURE.txt','SOURCE_COMMIT.txt','APK-METADATA.txt'):
            if name in archive.namelist():
                if archive.getinfo(name).file_size>65536: raise ValueError('Метаданные слишком большие.')
                files[name]=archive.read(name)
    for name in ('publish-android.sh','publish-update.py','compose.updates.yaml'):
        files[name]=(ROOT/name).read_bytes()
    files['UPDATE-ANDROID.md']=(ROOT/'PUBLISH-ANDROID.md').read_bytes()
    files['PACKAGE.sha256']=''.join(hashlib.sha256(data).hexdigest()+'  '+name+'\n' for name,data in sorted(files.items())).encode()
    output=Path(output).resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo('LiftControl-Android-update/'+name)
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=(0o100755 if name.endswith('.sh') else 0o100644)<<16
            archive.writestr(info,data)
    return release


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release_zip')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    release=package(args.release_zip,args.output)
    print('Готов пакет Android '+release['version']+' · сборка '+str(release['version_code']))
