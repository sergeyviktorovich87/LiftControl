#!/usr/bin/env python3
"""Publish immutable release files and atomically replace a read-only catalogue."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def publish(source, output, kind, version, notes='', version_code=None, expected_hash=None):
    source, output = Path(source), Path(output)
    if not source.is_file() or source.is_symlink():
        raise ValueError('Выберите обычный файл обновления.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}', version):
        raise ValueError('Неверный номер версии.')
    limit = 200 * 1024**2 if kind == 'android' else 600 * 1024**2
    if not 0 < source.stat().st_size <= limit:
        raise ValueError('Недопустимый размер файла.')
    if kind == 'android' and (type(version_code) is not int or not 0 < version_code <= 2100000000):
        raise ValueError('Нужен реальный versionCode APK из android-release.json.')
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    with (output / '.publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _publish_locked(source, output, kind, version, notes, version_code, expected_hash)


def _publish_locked(source, output, kind, version, notes, version_code, expected_hash):
    catalogue = output / 'release.json'
    if catalogue.is_symlink():
        raise ValueError('Ссылка вместо каталога обновлений.')
    current = json.loads(catalogue.read_text()) if catalogue.exists() else {}
    if not isinstance(current, dict):
        raise ValueError('Повреждён каталог обновлений. Текущая публикация сохранена.')
    with tempfile.NamedTemporaryFile(dir=output, prefix='.staging-', delete=False) as staged:
        staging = Path(staged.name)
        hash_value = hashlib.sha256()
        with source.open('rb') as stream:
            while block := stream.read(1024 * 1024):
                staged.write(block); hash_value.update(block)
        staged.flush(); os.fsync(staged.fileno())
    digest = hash_value.hexdigest()
    if expected_hash is not None and digest != expected_hash:
        staging.unlink(); raise ValueError('Контрольная сумма APK не совпала с данными сборки.')
    previous = current.get('android')
    if kind == 'android' and previous is not None:
        if not isinstance(previous, dict) or type(previous.get('version_code')) is not int:
            staging.unlink(); raise ValueError('Некорректная текущая версия Android в каталоге.')
        if version_code < previous['version_code']:
            staging.unlink(); raise ValueError('Нельзя публиковать более старую сборку APK.')
        if version_code == previous['version_code'] and digest != previous.get('sha256'):
            staging.unlink(); raise ValueError('С этим номером сборки уже опубликован другой APK. Нужен новый versionCode.')
    filename = f'LiftControl-{kind}-{version}-{digest[:12]}' + ('.apk' if kind == 'android' else '.zip')
    destination = output / filename
    if destination.is_symlink():
        staging.unlink(); raise ValueError('Ссылка вместо файла обновления.')
    os.chmod(staging, 0o644)
    os.replace(staging, destination)
    item = {'filename': filename, 'version': version, 'size': destination.stat().st_size, 'sha256': digest, 'notes': notes[:4000]}
    if kind == 'android': item['version_code'] = version_code
    current[kind] = item
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=output, prefix='.catalogue-', delete=False) as file:
        json.dump(current, file, ensure_ascii=False, indent=2); file.flush(); os.fsync(file.fileno())
    os.chmod(file.name, 0o644); os.replace(file.name, catalogue)
    return item


def inspect_android(directory):
    directory = Path(directory).resolve()
    data = json.loads((directory / 'android-release.json').read_text())['android']
    name = data['filename']
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,150}', name) or '..' in name:
        raise ValueError('Неверное имя APK в описании сборки.')
    if not re.fullmatch(r'[a-f0-9]{64}', data['sha256']):
        raise ValueError('Неверная контрольная сумма сборки.')
    source = directory / name
    if not source.is_file() or source.is_symlink() or source.stat().st_size != data['size']:
        raise ValueError('Размер APK не совпал с описанием сборки.')
    if type(data['version_code']) is not int or not 0 < data['version_code'] <= 2100000000:
        raise ValueError('Неверный versionCode сборки.')
    if not isinstance(data['version'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,39}', data['version']):
        raise ValueError('Неверная версия сборки.')
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        while block := stream.read(1024*1024): digest.update(block)
    if digest.hexdigest() != data['sha256']:
        raise ValueError('Контрольная сумма APK не совпала с данными сборки.')
    return data


def publish_android(directory, output):
    data = inspect_android(directory)
    source = Path(directory).resolve() / data['filename']
    return publish(source, output, 'android', data['version'], data.get('notes', ''), data['version_code'], data['sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Опубликовать обновление на сервере LiftControl')
    parser.add_argument('file', nargs='?'); parser.add_argument('--kind', choices=['android', 'panel'])
    parser.add_argument('--android-release', help='Папка распакованного APK с android-release.json')
    parser.add_argument('--check-android', action='store_true', help='Проверить APK без публикации')
    parser.add_argument('--version'); parser.add_argument('--version-code', type=int)
    parser.add_argument('--notes', default=''); parser.add_argument('--output', default='/opt/liftcontrol/updates')
    args = parser.parse_args()
    try:
        if args.check_android:
            if not args.android_release: raise ValueError('Укажите --android-release ПАПКА.')
            print(json.dumps(inspect_android(args.android_release),ensure_ascii=False)); raise SystemExit(0)
        if args.android_release and not args.file:
            item = publish_android(args.android_release, args.output)
        elif args.file and args.kind and args.version and not args.android_release:
            item = publish(args.file, args.output, args.kind, args.version, args.notes, args.version_code)
        else:
            raise ValueError('Укажите --android-release ПАПКА либо ФАЙЛ --kind ... --version ...')
        print(f"Опубликовано: {item['filename']} · SHA-256 {item['sha256']}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error))

