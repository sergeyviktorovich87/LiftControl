#!/usr/bin/env python3
"""Host-only updater. Trust a specific GitHub workflow on main, not arbitrary ZIPs."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile

REPO = 'sergeyviktorovich87/LiftControl'
API = f'https://api.github.com/repos/{REPO}'
WORKFLOW = f'{REPO}/.github/workflows/offline-patch.yml'
STATE = Path('/var/lib/liftcontrol-updater')
ROOT = Path('/opt/liftcontrol')
LIMIT = 100 * 1024**2
MAX_UNPACKED = 300 * 1024**2
VERSION_RE = re.compile(r'(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})')
HEX = re.compile(r'[a-f0-9]{64}')
COMMIT = re.compile(r'[a-f0-9]{40}')


def version(value):
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise ValueError('INVALID_VERSION')
    return tuple(map(int, value.split('.')))


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def download(url, destination, limit):
    # URLs are constructed from constants and validated numeric tags, never from
    # API-provided redirect targets. TLS verification stays enabled on redirects.
    run(['curl', '--disable', '--proto', '=https', '--proto-redir', '=https',
         '--fail', '--silent', '--show-error', '--location', '--max-redirs', '5',
         '--connect-timeout', '15', '--max-time', '180', '--max-filesize', str(limit),
         '--output', str(destination), url])
    if not 0 < destination.stat().st_size <= limit:
        raise ValueError('DOWNLOAD_SIZE')


def get_json(url, directory, name):
    file = directory / name
    download(url, file, 2 * 1024**2)
    return json.loads(file.read_bytes())


def health():
    result = run(['curl', '--disable', '--noproxy', '*', '--fail', '--silent',
                  '--show-error', '--max-time', '10',
                  'http://127.0.0.1:18080/api/health/'], capture_output=True)
    data = json.loads(result.stdout)
    version(data['version'])
    return data['version']


def select_release(data, installed):
    if data.get('draft') is not False or data.get('prerelease') is not False:
        return None
    tag = data.get('tag_name', '')
    if not isinstance(tag, str) or not tag.startswith('v'):
        raise ValueError('INVALID_TAG')
    target = tag[1:]
    if version(target) <= version(installed):
        return None
    name = f'LiftControl-v{target}-update.zip'
    required = {name: LIMIT, name + '.sha256': 4096, name + '.intoto.jsonl': 1024**2}
    assets = data.get('assets', [])
    for filename, maximum in required.items():
        matches = [a for a in assets if a.get('name') == filename]
        if len(matches) != 1 or matches[0].get('state') != 'uploaded':
            raise ValueError('MISSING_RELEASE_ASSET')
        size = matches[0].get('size')
        if type(size) is not int or not 0 < size <= maximum:
            raise ValueError('RELEASE_ASSET_SIZE')
    return target, name, required


def extract_checked(archive, directory, target, commit):
    prefix = f'LiftControl-v{target}-update'
    root = directory / prefix
    root.mkdir(mode=0o700)
    files = {}
    total = 0
    with zipfile.ZipFile(archive) as z:
        items = z.infolist()
        if not 0 < len(items) <= 10000:
            raise ValueError('ZIP_COUNT')
        for item in items:
            path = PurePosixPath(item.filename)
            if (item.is_dir() or len(path.parts) < 2 or path.parts[0] != prefix
                    or '/'.join(path.parts) != item.filename
                    or any(part in ('', '.', '..') for part in path.parts)
                    or '\\' in item.filename or '\x00' in item.filename
                    or stat.S_IFMT(item.external_attr >> 16) not in (0, stat.S_IFREG)
                    or item.flag_bits & 1):
                raise ValueError('UNSAFE_ZIP_PATH')
            rel = '/'.join(path.parts[1:])
            if rel in files:
                raise ValueError('DUPLICATE_ZIP_PATH')
            total += item.file_size
            if total > MAX_UNPACKED:
                raise ValueError('ZIP_SIZE')
            destination = root / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            count = 0
            with z.open(item) as source, destination.open('xb') as out:
                while chunk := source.read(1024**2):
                    count += len(chunk)
                    if count > item.file_size:
                        raise ValueError('ZIP_SIZE_MISMATCH')
                    digest.update(chunk)
                    out.write(chunk)
            if count != item.file_size:
                raise ValueError('ZIP_SIZE_MISMATCH')
            files[rel] = digest.hexdigest()
    manifest = {}
    for line in (root / 'PATCH.sha256').read_text().splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  (.+)', line)
        if not match or match[2] in manifest:
            raise ValueError('INVALID_PATCH_MANIFEST')
        manifest[match[2]] = match[1]
    if manifest != {k: v for k, v in files.items() if k != 'PATCH.sha256'}:
        raise ValueError('PATCH_MANIFEST_MISMATCH')
    if ((root / 'VERSION.txt').read_text().strip() != target or
            (root / 'SOURCE_COMMIT.txt').read_text().strip() != commit):
        raise ValueError('PACKAGE_IDENTITY_MISMATCH')
    if 'update-panel.sh' not in manifest:
        raise ValueError('MISSING_INSTALLER')
    return root


def migration_map(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*.py') if p.is_file()}


def api_container():
    base = ['docker', 'compose', '-f', 'compose.yaml', '-f', 'compose.api.yaml', '-f', 'compose.v04.yaml']
    for overlay in ('compose.v05.yaml', 'compose.v06.yaml', 'compose.push.yaml',
                    'compose.public.yaml', 'compose.updates.yaml', 'compose.fcm.yaml',
                    'compose.fcm-updates.yaml', 'compose.media.yaml', 'compose.uploads.yaml',
                    'compose.inspections.yaml'):
        if (ROOT / overlay).is_file():
            base.extend(['-f', overlay])
    result = run(base + ['ps', '-q', 'api'], cwd=ROOT, capture_output=True, text=True)
    ids = result.stdout.split()
    if len(ids) != 1 or not re.fullmatch('[a-f0-9]{12,64}', ids[0]):
        raise ValueError('API_CONTAINER_NOT_FOUND')
    return ids[0]


def installed_migrations():
    container = api_container()
    script = ("import pathlib,hashlib,json; r=pathlib.Path('/app/core/migrations'); "
              "print(json.dumps({p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() "
              "for p in r.rglob('*.py') if p.is_file()}))")
    return json.loads(run(['docker', 'exec', container, 'python', '-c', script],
                          capture_output=True).stdout)


def update(allow_migrations=False, retry=False, check_only=False, expected_target=None):
    installed = health()
    print('INSTALLED', installed, flush=True)
    with tempfile.TemporaryDirectory(prefix='download-', dir=STATE) as temp:
        directory = Path(temp)
        release = get_json(API + '/releases/latest', directory, 'release.json')
        selected = select_release(release, installed)
        if selected is None:
            print('NO_NEW_STABLE_RELEASE', flush=True)
            return ('current', '')
        target, name, assets = selected
        if expected_target is not None and expected_target != target:
            return ('changed', target)
        if check_only:
            return ('available', target)
        failed = STATE / f'failed-{target}'
        if failed.exists() and not retry:
            print('BLOCKED_PREVIOUS_FAILURE', target, 'use --retry after inspection', flush=True)
            return ('blocked', target)
        commit = get_json(API + '/commits/v' + target, directory, 'commit.json').get('sha', '')
        if not COMMIT.fullmatch(commit):
            raise ValueError('INVALID_TAG_COMMIT')
        print('DOWNLOAD', target, flush=True)
        for filename, maximum in assets.items():
            download(f'https://github.com/{REPO}/releases/download/v{target}/{filename}',
                     directory / filename, maximum)
        archive = directory / name
        expected = (directory / (name + '.sha256')).read_text().strip()
        if not re.fullmatch(r'[a-f0-9]{64}  ' + re.escape(name), expected):
            raise ValueError('INVALID_CHECKSUM')
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if expected[:64] != digest:
            raise ValueError('ARCHIVE_CHECKSUM_MISMATCH')
        # Verify the signed provenance, not just a mutable checksum beside the ZIP.
        run(['gh', 'attestation', 'verify', str(archive), '--bundle', str(directory / (name + '.intoto.jsonl')),
             '--repo', REPO, '--signer-workflow', WORKFLOW, '--source-ref', 'refs/heads/main',
             '--source-digest', commit, '--deny-self-hosted-runners'])
        package = extract_checked(archive, directory, target, commit)
        print('VERIFIED', target, digest, flush=True)
        candidate = migration_map(package / 'payload/core/migrations')
        if not candidate:
            raise ValueError('MIGRATIONS_MISSING')
        if not allow_migrations and candidate != installed_migrations():
            print('REQUIRES_MANUAL_MIGRATION_APPROVAL', target,
                  'run updater --allow-migrations after reviewing release', flush=True)
            return ('migration_approval', target)
        # Existing installer locks and validates expected version again. Do not
        # automatically restore a database snapshot over newly written data.
        if health() != installed:
            raise ValueError('VERSION_CHANGED_BEFORE_INSTALL')
        env = dict(os.environ, LIFTCONTROL_AUTO_EXPECTED_VERSION=installed)
        try:
            run(['bash', str(package / 'update-panel.sh')], cwd=package, env=env)
            if health() != target:
                raise ValueError('POST_INSTALL_VERSION_MISMATCH')
        except subprocess.CalledProcessError as error:
            if error.returncode == 75:
                print('DEFERRED_ACTIVE_ENTRAPMENT', target, flush=True)
                return ('deferred', target)
            failed.write_text(digest + '\n')
            raise
        except (OSError, ValueError):
            failed.write_text(digest + '\n')
            raise
        failed.unlink(missing_ok=True)
        print('INSTALLED_OK', target, flush=True)
        return ('installed', target)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-migrations', action='store_true')
    parser.add_argument('--retry', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    os.umask(0o077)
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = STATE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise SystemExit('UNSAFE_STATE_DIRECTORY')
    with (STATE / 'lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('UPDATE_ALREADY_RUNNING', flush=True)
            return
        update(args.allow_migrations, args.retry)


if __name__ == '__main__':
    main()
