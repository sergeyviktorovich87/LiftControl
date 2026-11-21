"""Exercise the real installer and a DB+media restore on a disposable CI runner."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request


def run(*args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package', required=True)
    parser.add_argument('--baseline-image', default='liftcontrol-api:baseline08')
    options=parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.geteuid()!=0:
        raise RuntimeError('Only an isolated root GitHub Actions runner is supported')
    root=Path('/opt/liftcontrol')
    if root.exists():raise RuntimeError('Refusing to overwrite an existing installation')
    root.mkdir(parents=True,mode=0o755)
    package=Path(options.package).resolve()
    version=(package/'VERSION.txt').read_text().strip()
    compose='''name: lc-media-installer-ci
services:
  db:
    image: postgres:18
    environment:
      POSTGRES_PASSWORD: ci-only-database-password
      POSTGRES_DB: liftcontrol
    volumes: [ci_database:/var/lib/postgresql]
  api:
    image: liftcontrol-api:0.6
    ports: ["127.0.0.1:18080:8000"]
    environment: &api_env
      DJANGO_DEBUG: "True"
      DB_ENGINE: postgresql
      DB_USER: liftapp
      DB_PASSWORD: ci-only-application-password
      DB_HOST: db
      DB_NAME: liftcontrol
      DJANGO_MEDIA_ROOT: /app/private_media
    volumes: [ci_media:/app/private_media]
  migrate:
    image: liftcontrol-api:0.6
    profiles: [maintenance]
    environment:
      <<: *api_env
      DB_USER: postgres
      DB_PASSWORD: ci-only-database-password
    entrypoint: [python, manage.py, migrate, --noinput]
volumes:
  ci_database: {}
  ci_media: {}
'''
    (root/'compose.yaml').write_text(compose)
    for name in ('compose.api.yaml','compose.v04.yaml','compose.v06.yaml'):(root/name).write_text('services: {}\n')
    command=['docker','compose','-f',str(root/'compose.yaml')]
    try:
        run('docker','tag',options.baseline_image,'liftcontrol-api:0.6')
        run(*command,'up','-d','db',cwd=root)
        for attempt in range(60):
            ready=subprocess.run(command+['exec','-T','db','pg_isready','-h','127.0.0.1','-U','postgres','-d','liftcontrol'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(1)
        sql="CREATE ROLE liftapp LOGIN PASSWORD 'ci-only-application-password'; CREATE SCHEMA app AUTHORIZATION postgres; GRANT USAGE ON SCHEMA app TO liftapp; ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO liftapp; ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT USAGE,SELECT ON SEQUENCES TO liftapp;"
        run(*command,'exec','-T','db','psql','-U','postgres','-d','liftcontrol','-v','ON_ERROR_STOP=1','-c',sql,cwd=root)
        run(*command,'--profile','maintenance','run','--rm','--no-deps','migrate',cwd=root)
        seed="""import io; from PIL import Image; from django.contrib.auth import get_user_model; from django.core.files.base import ContentFile; from core.models import Building,Elevator,Ticket,TicketPhoto; b=Building.objects.create(name='Keep building',address='Keep address'); e=Elevator.objects.create(building=b,inventory_number='KEEP-001'); t=Ticket.objects.create(elevator=e,title='Keep ticket',description='Keep report'); u=get_user_model().objects.create_user('restore-check'); buffer=io.BytesIO();Image.new('RGB',(16,16),'green').save(buffer,format='PNG'); p=TicketPhoto(organization_id=1,ticket=t,uploaded_by=u);p.file.save('legacy.png',ContentFile(buffer.getvalue()));print('LEGACY_MEDIA_SEEDED')"""
        run(*command,'run','--rm','--no-deps','-T','--entrypoint','python','-e','DB_USER=postgres','-e','DB_PASSWORD=ci-only-database-password','api','manage.py','shell','-c',seed,cwd=root)
        run(*command,'up','-d','api',cwd=root)
        for attempt in range(40):
            try:
                urllib.request.urlopen('http://127.0.0.1:18080/api/health/',timeout=1).close();break
            except OSError:time.sleep(1)
        run('bash',str(package/'update-panel.sh'),cwd=package)
        current=command+['-f',str(root/'compose.updates.yaml'),'-f',str(root/'compose.media.yaml')]
        check=f"""import hashlib;from core.models import Ticket,TicketPhoto,MediaAsset;from django.core.files.storage import default_storage;from django.test import Client;t=Ticket.objects.get();p=TicketPhoto.objects.get();a=MediaAsset.objects.get();assert t.description=='Keep report';assert a.file.name.startswith('org_1/');assert p.asset_id==a.pk;assert p.file.name!=a.file.name;assert default_storage.exists(p.file.name);assert hashlib.sha256(p.file.read()).hexdigest()==a.sha256;assert hashlib.sha256(a.file.read()).hexdigest()==a.sha256;assert a.preview.size>0;assert Client(HTTP_HOST='localhost').get('/api/health/').json()['version']=={version!r};print('MIGRATED ORIGINAL AND LEGACY PATH VERIFIED')"""
        run(*current,'exec','-T','api','python','manage.py','shell','-c',check,cwd=root)
        # A second run must neither overwrite files nor duplicate registered media.
        run('bash',str(package/'update-panel.sh'),cwd=package)
        archive=sorted(Path('/srv/liftcontrol-data/backups').glob('*.tar.gz'))[-1]
        restore=Path('/tmp/lc-media-restore');restore.mkdir(mode=0o755)
        run('python3',str(root/'backup-media.py'),'--verify',str(archive))
        with tarfile.open(archive) as data:data.extractall(restore,filter='data')
        run('chown','-R','10001:10001',str(restore))
        run(*current,'exec','-T','db','createdb','-U','postgres','lc_media_restore',cwd=root)
        with (restore/'database.dump').open('rb') as file:
            run(*current,'exec','-T','db','pg_restore','-U','postgres','-d','lc_media_restore','--single-transaction','--exit-on-error',stdin=file,cwd=root)
        run(*current,'run','--rm','--no-deps','-T','-e','DB_NAME=lc_media_restore','-e','DJANGO_MEDIA_ROOT=/restore/media','-v',str(restore/'media')+':/restore/media:ro','--entrypoint','python','api','manage.py','shell','-c',check,cwd=root)
        print('REAL INSTALLER, REPEATED MIGRATION AND DATABASE+MEDIA RESTORE VERIFIED')
    finally:
        subprocess.run(command+['down','--volumes','--remove-orphans'],cwd=root,check=False)


if __name__=='__main__':main()
