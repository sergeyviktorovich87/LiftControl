#!/usr/bin/env python3
"""Publish immutable release files and atomically replace a read-only catalogue."""
import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def publish(source, output, kind, version, notes='', version_code=None):
    source, output = Path(source), Path(output)
    if not source.is_file() or source.is_symlink():
        raise ValueError('Выберите обычный файл обновления.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}', version):
        raise ValueError('Неверный номер версии.')
    limit = 200 * 1024**2 if kind == 'android' else 600 * 1024**2
    if not 0 < source.stat().st_size <= limit:
        raise ValueError('Недопустимый размер файла.')
    if kind == 'android' and (not isinstance(version_code, int) or not 0 < version_code <= 2100000000):
        raise ValueError('Нужен реальный versionCode APK из android-release.json.')
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    with tempfile.NamedTemporaryFile(dir=output, prefix='.staging-', delete=False) as staged:
        staging = Path(staged.name)
        hash_value = hashlib.sha256()
        with source.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                staged.write(block); hash_value.update(block)
        staged.flush(); os.fsync(staged.fileno())
    digest = hash_value.hexdigest()
    filename = f'LiftControl-{kind}-{version}-{digest[:12]}' + ('.apk' if kind == 'android' else '.zip')
    destination = output / filename
    if destination.is_symlink():
        staging.unlink(); raise ValueError('Ссылка вместо файла обновления.')
    os.chmod(staging, 0o644)
    os.replace(staging, destination)
    item = {'filename': filename, 'version': version, 'size': destination.stat().st_size, 'sha256': digest, 'notes': notes[:4000]}
    if kind == 'android': item['version_code'] = version_code
    catalogue = output / 'release.json'
    current = json.loads(catalogue.read_text()) if catalogue.exists() else {}
    current[kind] = item
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output, prefix='.catalogue-', delete=False) as file:
        json.dump(current, file, ensure_ascii=False, indent=2); file.flush(); os.fsync(file.fileno())
    os.chmod(file.name, 0o644); os.replace(file.name, catalogue)
    return item


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Опубликовать обновление на сервере LiftControl')
    parser.add_argument('file'); parser.add_argument('--kind', choices=['android', 'panel'], required=True)
    parser.add_argument('--version', required=True); parser.add_argument('--version-code', type=int)
    parser.add_argument('--notes', default=''); parser.add_argument('--output', default='/opt/liftcontrol/updates')
    args = parser.parse_args()
    try:
        item = publish(args.file, args.output, args.kind, args.version, args.notes, args.version_code)
        print(f"Опубликовано: {item['filename']} · SHA-256 {item['sha256']}")
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))
