#!/usr/bin/env python3
"""Export a CLEAN test-only public snapshot. No history, secrets or deployment."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOTS = ('backend', 'web', 'mobile', 'tests')
OMIT = {
    'backend/.env.example',
    'backend/core/megapolis_data.py',
    'backend/core/management/commands/import_megapolis.py',
    'backend/core/management/commands/seed_demo.py',
    'mobile/README.md',
    'mobile/.metadata',
}
OMIT_PARTS = {
    '.git', '.github', '.gradle', '.dart_tool', 'node_modules', '__pycache__',
    '.venv', 'venv', 'dist', 'build', '.idea', '.vscode', 'private_media',
    'backups', '.pytest_cache', 'coverage',
}
OMIT_NAMES = {
    'google-services.json', 'key.properties', 'local.properties',
    '.env', '.env.production', '.env.local', 'credentials.json',
    'service-account.json', 'id_rsa', 'id_ed25519',
}
OMIT_EXT = {'.jks','.keystore','.pem','.key','.p12','.pfx','.sqlite',
            '.sqlite3','.db','.dump','.zip','.apk','.aab','.tar','.log',
            '.sql','.bak'}
TEXT_EXT = {'.py','.dart','.kt','.kts','.java','.jsx','.js','.tsx',
            '.ts','.css','.html','.xml','.yaml','.yml','.json',
            '.properties','.lock','.toml','.txt','.md','.sh','.gradle'}
TEXT_NAMES = {'.gitignore','.dockerignore','Dockerfile','Makefile'}
BINARY = {'mobile/android/app/src/main/res/raw/entrapment_alert.wav'}

REPLACE = {
    'ООО «Эверест»':'ООО «Организация Бета»',
    'Сергей А.':'Демо-администратор',
    'Мегаполис':'Организация Альфа',
    'Эверест':'Организация Бета',
    'Сергей':'Демо-пользователь',
    'Николаи':'Иванов', 'Шатравка':'Петров',
    'Кантемиров':'Кузнецов', 'Андросов':'Смирнов',
    'Игнатьевское шоссе':'Учебный проспект',
    'Воронкова':'Тестовая улица',
    '50 лет Октября':'Учебная улица',
    'Чайка Smart':'Дом Альфа',
    'Причал':'Дом Бета',
    'Благовещенск':'Демо-город',
    'Ленина':'Учебная',
}
PRIVATE = re.compile(
    r'Мегаполис|Эверест|Игнатьевск|Воронков|Кантемиров|Андросов|'
    r'Шатравк|Николаи|50 лет Октября|Чайка Smart|Причал|Благовещенск|Сергей А\.',
    re.I,
)
CREDENTIAL = re.compile(
    r'-----BEGIN [^-]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|'
    r'gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|'
    r'AIza[0-9A-Za-z_-]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{25,}',
    re.I,
)
IP = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')

WORKFLOW = """name: Public LiftControl checks (NO secrets or releases)
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
concurrency:
  group: public-liftcontrol-tests
  cancel-in-progress: true
jobs:
  backend:
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    env:
      DJANGO_DEBUG: 'True'
      DJANGO_SECRET_KEY: 'fake-key-public-test-only'
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: |
          sudo apt-get update -qq
          sudo apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core
      - run: python -m pip install -r backend/requirements.txt
      - run: python -m compileall -q backend
      - name: Verify migrations
        working-directory: backend
        run: python manage.py makemigrations --check --dry-run core
      - name: Django tests
        working-directory: backend
        run: |
          python manage.py migrate --noinput
          python manage.py test core --verbosity 2
  web:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: npm ci --no-audit --no-fund
        working-directory: web
      - run: npm run build -- --base=/static/web/
        working-directory: web
  android:
    runs-on: ubuntu-24.04
    timeout-minutes: 35
    env:
      CI: 'true'
      FLUTTER_SUPPRESS_ANALYTICS: 'true'
      DART_SUPPRESS_ANALYTICS: 'true'
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: subosito/flutter-action@1a449444c387b1966244ae4d4f8c696479add0b2
        with:
          flutter-version: '3.47.9'
          cache: true
      - run: flutter pub get --enforce-lockfile
        working-directory: mobile
      - run: flutter analyze --no-pub
        working-directory: mobile
      - run: flutter test --no-pub --reporter expanded
        working-directory: mobile
      - run: |
          python tool/prepare_gradle.py
          flutter build apk --debug --target-platform android-arm64
        working-directory: mobile
# Intentionally NO signing, publishing, artifact uploads, production credentials.
"""
README = """# LiftControl - public CI snapshot

Contains only cleaned source for test and debug compile.
No production database, no original Git history, no actual staff or customer
records, no server deployment scripts, no signing keys or Firebase credentials.

The original LiftControl repository remains PRIVATE.
The public repository is NOT a release channel.
Do not install a DEBUG APK over an already signed app.
No open-source license is granted by publication.
"""
GITIGNORE = """.env
*.jks
*.keystore
*.pem
*.p12
*.key
google-services.json
key.properties
local.properties
__pycache__/
node_modules/
build/
dist/
.dart_tool/
.venv/
"""


def allowed(rel):
    name=rel.as_posix()
    return (rel.parts and rel.parts[0] in ROOTS
        and name not in OMIT
        and rel.name not in OMIT_NAMES
        and not any(p in OMIT_PARTS for p in rel.parts)
        and rel.suffix.lower() not in OMIT_EXT
        and (name in BINARY or rel.suffix.lower() in TEXT_EXT or rel.name in TEXT_NAMES))


def sanitized(content, rel):
    if rel.as_posix()=='backend/core/tests_organizations.py':
        content, n = re.subn(r'\nclass MegapolisImportTests\(TestCase\):[\s\S]*$',
                             '\n', content, count=1)
        if n!=1:
            raise ValueError('Unexpected customer import tests: review manually')
    for before, after in REPLACE.items():
        content=content.replace(before, after)
    if PRIVATE.search(content):
        raise ValueError('Unredacted customer/staff data in '+str(rel))
    if CREDENTIAL.search(content):
        raise ValueError('Potential credential in '+str(rel))
    if any(ip.group() not in {'127.0.0.1','0.0.0.0'}
           for ip in IP.finditer(content)):
        raise ValueError('Unreviewed network address in '+str(rel))
    return content


def export(source, dest):
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if not (source/'backend/manage.py').is_file():
        raise ValueError('Source is not a LiftControl checkout')
    if source==dest or source in dest.parents or dest in source.parents:
        raise ValueError('Export must be outside the private checkout')
    if dest.exists() and (dest.is_symlink() or any(dest.iterdir())):
        raise ValueError('Destination must be empty, not a symlink')
    prepared=[]
    for root in ROOTS:
        for path in (source/root).rglob('*'):
            if path.is_symlink():
                raise ValueError('Symlink requires manual review: '+str(path))
            if not path.is_file():
                continue
            rel=path.relative_to(source)
            if not allowed(rel):
                continue
            if path.stat().st_size>1024*1024:
                raise ValueError('Oversized source file: '+str(rel))
            payload=(path.read_bytes() if rel.as_posix() in BINARY
                else sanitized(path.read_text('utf-8'),rel).encode('utf-8'))
            prepared.append((rel,payload))
    if len(prepared)<40:
        raise ValueError('Unexpectedly small snapshot; aborting')
    # No files are written before every selected source passes security checks.
    dest.mkdir(parents=True,exist_ok=True)
    for rel, payload in prepared:
        out=dest/rel
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_bytes(payload)
    ci=dest/'.github/workflows/public-ci.yml'
    ci.parent.mkdir(parents=True,exist_ok=True)
    ci.write_text(WORKFLOW,encoding='utf-8')
    (dest/'README.md').write_text(README,encoding='utf-8')
    (dest/'.gitignore').write_text(GITIGNORE,encoding='utf-8')
    manifest={str(rel):hashlib.sha256(payload).hexdigest() for rel,payload in prepared}
    (dest/'PUBLIC_SNAPSHOT_MANIFEST.json').write_text(
        json.dumps({'kind':'sanitized-test-snapshot','files':manifest},indent=2)
        +'\n',encoding='utf-8')
    return len(prepared)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,default=Path.cwd())
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    print('Sanitized source files:',export(a.source,a.output))
    print('No remote or GitHub repository was changed.')
