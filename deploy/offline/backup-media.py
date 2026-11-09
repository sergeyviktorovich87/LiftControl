"""Consistent database + immutable media backup, without pausing dispatch.

Publication writes the complete immutable file before its database transaction
commits. No committed files are removed; copying after pg_dump therefore retains
every file referenced by its database snapshot. Each archived byte is hashed.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def archive_files(database, media, output):
    entries=[('database.dump',Path(database))]+[('media/'+p.relative_to(media).as_posix(),p) for p in sorted(Path(media).rglob('*')) if p.is_file()]
    manifest={}
    with tarfile.open(output,'w:gz') as archive:
        for name,path in entries:
            if path.is_symlink():raise ValueError('BACKUP_SYMLINK')
            before=path.stat()
            with path.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
            archive.add(path,arcname=name,recursive=False)
            after=path.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('BACKUP_SOURCE_CHANGED')
            manifest[name]={'size':before.st_size,'sha256':digest}
        data=json.dumps(manifest,sort_keys=True).encode()
        info=tarfile.TarInfo('manifest.json');info.size=len(data);info.mode=0o600
        archive.addfile(info,io.BytesIO(data))
    verify(output)


def verify(path):
    with tarfile.open(path,'r:gz') as archive:
        manifest=json.load(archive.extractfile('manifest.json'))
        for name,item in manifest.items():
            if name.startswith('/') or '..' in Path(name).parts:raise ValueError('BACKUP_PATH')
            member=archive.getmember(name)
            if not member.isfile() or member.size!=item['size']:raise ValueError('BACKUP_MEMBER')
            if hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()!=item['sha256']:raise ValueError('BACKUP_HASH')
    return len(manifest)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify');parser.add_argument('--after-update',action='store_true');options=parser.parse_args()
    if options.verify:
        print('BACKUP_VERIFIED',verify(options.verify));return
    if os.geteuid()!=0:raise ValueError('Run with sudo')
    root=Path('/opt/liftcontrol');media=Path('/srv/liftcontrol-data/media');backups=Path('/srv/liftcontrol-data/backups')
    backups.mkdir(parents=True,exist_ok=True,mode=0o700)
    # The installer already owns this lock while taking its first full backup.
    lock=(root/'.panel-update.lock').open('a')
    if not options.after_update:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    command=['docker','compose']
    for name in ('compose.yaml','compose.api.yaml','compose.v04.yaml','compose.v05.yaml','compose.v06.yaml','compose.push.yaml','compose.public.yaml','compose.updates.yaml','compose.fcm.yaml','compose.media.yaml'):
        if (root/name).is_file():command.extend(['-f',str(root/name)])
    media_bytes=sum(p.stat().st_size for p in media.rglob('*') if p.is_file())
    database_bytes=int(subprocess.check_output(command+['exec','-T','db','psql','-U','postgres','-d','liftcontrol','-Atc','SELECT pg_database_size(current_database())'],cwd=root,text=True).strip())
    # Stop creating archives before they could consume the application's last
    # gigabyte. Original media and previous backups are never purged implicitly.
    if shutil.disk_usage(backups).free < media_bytes*2+database_bytes*2+1024**3:
        raise ValueError('BACKUP_SPACE_LOW: free space or configure archive retention')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    target=backups/f'liftcontrol-{stamp}.tar.gz'
    with tempfile.TemporaryDirectory(prefix='.backup-',dir=backups) as temporary:
        database=Path(temporary)/'database.dump'
        with database.open('wb') as file:
            subprocess.run(command+['exec','-T','db','pg_dump','-U','postgres','-d','liftcontrol','-Fc'],stdout=file,check=True,cwd=root)
        with database.open('rb') as file:
            subprocess.run(command+['exec','-T','db','pg_restore','--list'],stdin=file,stdout=subprocess.DEVNULL,check=True,cwd=root)
        output=Path(temporary)/'backup.tar.gz';archive_files(database,media,output);os.replace(output,target)
    config=Path('/opt/liftcontrol/backup-remote.txt')
    remote=config.read_text().strip() if config.exists() else ''
    if remote:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+:/[A-Za-z0-9_./-]+',remote):raise ValueError('Invalid remote destination')
        subprocess.run(['scp','-p','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',str(target),remote.rstrip('/')+'/'],check=True,timeout=600)
        host,directory=remote.split(':',1)
        remote_hash=subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',host,'sha256sum',directory.rstrip('/')+'/'+target.name],timeout=60,text=True).split()[0]
        with target.open('rb') as file:local_hash=hashlib.file_digest(file,'sha256').hexdigest()
        if remote_hash!=local_hash:raise ValueError('REMOTE_BACKUP_HASH_MISMATCH')
        print('LOCAL_AND_OFFSITE_BACKUP_VERIFIED',target.name)
    else:
        print('LOCAL_BACKUP_VERIFIED; OFFSITE_NOT_CONFIGURED',target.name)


if __name__=='__main__':main()
