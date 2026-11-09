"""Run as the API UID, with the old container mounts read-only and a new bind.

No removal, overwriting, links or shell commands. A partial copy is resumable.
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tempfile


def copy(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_dir() or not destination.is_dir():
        raise ValueError('MEDIA_DIRECTORY_MISSING')
    if source == destination:
        return 0
    count = 0
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('MEDIA_SYMLINK_REJECTED')
        target = destination/path.relative_to(source)
        if target.is_symlink():
            raise ValueError('MEDIA_TARGET_SYMLINK_REJECTED')
        if path.is_dir():
            target.mkdir(parents=True,exist_ok=True,mode=0o700)
            continue
        if not path.is_file():
            raise ValueError('MEDIA_SPECIAL_FILE_REJECTED')
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with path.open('rb') as file:
            digest = hashlib.file_digest(file,'sha256').digest()
        if target.exists():
            with target.open('rb') as file:
                if hashlib.file_digest(file,'sha256').digest() != digest:
                    raise ValueError('MEDIA_COPY_CONFLICT')
            continue
        fd, temp = tempfile.mkstemp(prefix='.copy-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as file, path.open('rb') as original:
                shutil.copyfileobj(original,file,1024*1024);file.flush();os.fsync(file.fileno())
            with open(temp,'rb') as file:
                if hashlib.file_digest(file,'sha256').digest() != digest:
                    raise ValueError('MEDIA_COPY_HASH_MISMATCH')
            os.replace(temp,target)
            count += 1
        finally:
            if os.path.exists(temp):os.unlink(temp)
    return count


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default='/app/private_media');parser.add_argument('--destination',default='/new-media')
    options=parser.parse_args()
    print('MEDIA_FILES_COPIED',copy(options.source,options.destination))
