#!/usr/bin/env python3
"""Public HTTPS deployment for an existing LiftControl 0.6/0.7/0.8/0.9; never resets data."""
import argparse
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path('/opt/liftcontrol')
NGINX_IMAGE = 'nginxinc/nginx-unprivileged:1.30.6-alpine'
CERTBOT_IMAGE = 'certbot/certbot:v5.9.0'
CERTIFICATE_NAME = 'liftcontrol-public'


def normalize_host(value):
    value = str(value).strip().rstrip('.').lower()
    if not value or any(c in value for c in '/\\:@?#\t\r\n $`\'"'):
        raise ValueError('Нужен публичный IPv4 или домен без https://, порта и пути.')
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        if re.fullmatch(r'[0-9.]+', value):
            raise ValueError('Некорректный IP-адрес.')
        try:
            value = value.encode('idna').decode('ascii')
        except UnicodeError as exc:
            raise ValueError('Некорректное доменное имя.') from exc
        labels = value.split('.')
        if len(value) > 253 or len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in labels):
            raise ValueError('Некорректное доменное имя.')
        if labels[-1] in ('localhost','local','internal','invalid'):
            raise ValueError('Нужен публичный адрес.')
        return value, False
    if address.version != 4 or not address.is_global:
        raise ValueError('Нужен публичный IPv4, например адрес вашего VPS.')
    return str(address), True


def public_overlay(host):
    return {
        'services': {
            'api': {'environment': {
                'DJANGO_ALLOWED_HOSTS': host + ',127.0.0.1,localhost',
                'DJANGO_BEHIND_HTTPS_PROXY': 'True',
            }},
            'edge': {
                'image': NGINX_IMAGE,
                'user': '101:101', 'restart': 'unless-stopped', 'read_only': True,
                'ports': ['80:8080','443:8443'], 'networks': ['frontend'],
                'volumes': ['./public/nginx:/etc/nginx/conf.d:ro', './public/runtime:/etc/nginx/runtime:ro',
                            './public/acme:/var/www/acme:ro'],
                'tmpfs': ['/tmp:size=64m,mode=1777'],
                'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'],
                'logging': {'driver':'json-file','options':{'max-size':'5m','max-file':'3'}},
                'healthcheck': {'test':['CMD','nginx','-t'],'interval':'30s','timeout':'5s','retries':3},
            },
        },
    }


def proxy_include():
    return '''resolver 127.0.0.11 valid=10s ipv6=off;
set $liftcontrol_backend api:8000;
proxy_pass http://$liftcontrol_backend;
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header Connection "";
proxy_request_buffering off;
proxy_read_timeout 60s;
proxy_connect_timeout 5s;
'''


def nginx_config(host, tls):
    # Host is validated before rendering. The ACME location contains public challenges only.
    common = '''server_tokens off;
log_format liftcontrol '$remote_addr "$request_method $uri" $status $body_bytes_sent $request_time';
access_log /dev/stdout liftcontrol;
map $request_method $liftcontrol_login_key { default ""; POST $binary_remote_addr; }
limit_req_zone $liftcontrol_login_key zone=liftcontrol_login:10m rate=10r/m;
'''
    http = f'''server {{
    listen 8080 default_server;
    server_name {host};
    location ^~ /.well-known/acme-challenge/ {{ root /var/www/acme; try_files $uri =404; }}
    location / {{ {'return 308 https://' + host + '$request_uri;' if tls else 'return 503;'} }}
}}
'''
    if not tls:
        return common + http
    return common + http + f'''server {{
    listen 8443 ssl default_server;
    server_name {host};
    if ($host != "{host}") {{ return 444; }}
    ssl_certificate /etc/nginx/runtime/current/fullchain.pem;
    ssl_certificate_key /etc/nginx/runtime/current/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:TLS:5m;
    ssl_session_timeout 1d;
    client_max_body_size 21m;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    location = /login/ {{
        limit_req zone=liftcontrol_login burst=20 nodelay;
        limit_req_status 429;
        include /etc/nginx/conf.d/proxy.inc;
    }}
    location = /admin/login/ {{
        limit_req zone=liftcontrol_login burst=20 nodelay;
        limit_req_status 429;
        include /etc/nginx/conf.d/proxy.inc;
    }}
    location / {{ include /etc/nginx/conf.d/proxy.inc; }}
}}
'''


def certbot_arguments(host, is_ip, dry_run=False, email=None):
    args = ['certonly','--non-interactive','--agree-tos','--webroot','--webroot-path','/webroot',
            '--cert-name',CERTIFICATE_NAME,'--key-type','ecdsa','--renew-with-new-domains']
    args += ['--ip-address',host,'--required-profile','shortlived'] if is_ip else ['-d',host]
    args += ['--email',email] if email else ['--register-unsafely-without-email']
    args += ['--dry-run'] if dry_run else ['--keep-until-expiring']
    return args


def atomic_write(path, text, mode=0o600):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def sync_certificate(folder):
    """Switch a complete certificate/key pair together; NGINX reads as UID 101."""
    folder = Path(folder)
    source = folder/'letsencrypt'/'live'/CERTIFICATE_NAME
    for name in ('fullchain.pem','privkey.pem'):
        if not (source/name).is_file():
            raise RuntimeError('Certbot не сохранил сертификат и закрытый ключ.')
    runtime = folder/'runtime'
    runtime.mkdir(exist_ok=True, mode=0o755)
    version = Path(tempfile.mkdtemp(prefix='cert-', dir=runtime))
    os.chown(version,101,101)
    os.chmod(version,0o700)
    for name in ('fullchain.pem','privkey.pem'):
        target = version/name
        # Write the TLS private key without ever exposing it in process output.
        with open(target,'xb') as output:
            os.chmod(target,0o600)
            output.write((source/name).read_bytes())
        os.chown(target,101,101)
        os.chmod(target,0o400)
    previous=os.readlink(runtime/'current') if (runtime/'current').is_symlink() else None
    temporary = runtime/'.current-next'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(version.name, target_is_directory=True)
    os.replace(temporary,runtime/'current')
    # Keep the last 3 complete pairs for rollback; never delete the selected pair.
    versions = sorted(runtime.glob('cert-*'),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in versions[3:]:
        if old != version and old.name!=previous:
            shutil.rmtree(old)


def compose(root=ROOT, public=True, stage=None):
    root=Path(root)
    args=['docker','compose','-f',str(root/'compose.yaml'),'-f',str(root/'compose.api.yaml')]
    for name in ('compose.v04.yaml','compose.v05.yaml','compose.v06.yaml','compose.push.yaml',
                 'compose.updates.yaml','compose.fcm.yaml'):
        if (root/name).is_file():
            args += ['-f',str(root/name)]
    if stage:
        args += ['-f',str(stage)]
    elif public and (root/'compose.public.yaml').is_file():
        args += ['-f',str(root/'compose.public.yaml')]
    return args


class Access:
    def __init__(self, root=ROOT):
        self.root=Path(root)
        self.folder=self.root/'public'
        self.log=None

    def run(self,args,input=None,capture=False,check=True):
        result=subprocess.run([str(x) for x in args],input=input,text=True,capture_output=True)
        if self.log:
            self.log.write(result.stdout+result.stderr)
            self.log.flush()
        if check and result.returncode:
            raise RuntimeError(f'Команда {args[0]} завершилась с кодом {result.returncode}. Подробности: {self.folder}/setup.log')
        return result.stdout if capture else result

    def message(self,text):
        print(text,flush=True)
        if self.log:
            self.log.write(text+'\n');self.log.flush()

    def health(self):
        for attempt in range(40):
            try:
                with urllib.request.urlopen('http://127.0.0.1:18080/api/health/',timeout=3) as response:
                    data=json.load(response)
                if data.get('version') in ('0.6', '0.7', '0.8', '0.9'):
                    return
            except (OSError,ValueError):
                pass
            time.sleep(.5)
        raise RuntimeError('Нужна установленная и запущенная LiftControl 0.6, 0.7, 0.8 или 0.9.')

    def certbot(self,args):
        return self.run(['docker','run','--rm','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
            '--tmpfs','/tmp:size=32m,mode=1777',
            '-v',f'{self.folder}/letsencrypt:/etc/letsencrypt',
            '-v',f'{self.folder}/work:/var/lib/letsencrypt',
            '-v',f'{self.folder}/certbot-logs:/var/log/letsencrypt',
            '-v',f'{self.folder}/acme:/webroot',CERTBOT_IMAGE]+args)

    def tls_health(self,host):
        raw=self.run(['curl','--fail','--silent','--show-error','--max-time','15',
            '--noproxy','*','--connect-to',f'{host}:443:127.0.0.1:443',f'https://{host}/api/health/'],capture=True)
        if json.loads(raw).get('version') not in ('0.6', '0.7', '0.8', '0.9'):
            raise RuntimeError('Проверка HTTPS не подтвердила совместимую версию LiftControl.')

    def setup(self, host, email=None):
        host,is_ip=normalize_host(host)
        source=Path(__file__).resolve().parent
        if not (self.root/'compose.v06.yaml').is_file():
            raise RuntimeError('Сначала установите LiftControl 0.6.')
        self.health()
        original=compose(self.root)
        self.run(original+['exec','-T','api','python','manage.py','migrate','--check'])
        statefile=self.folder/'state.json'
        previous_state=json.loads(statefile.read_text()) if statefile.is_file() else {}
        if previous_state.get('installed') and previous_state.get('host')!=host:
            raise RuntimeError('Уже настроен другой адрес. Сначала выполните rollback-public.sh; данные приложения сохранятся.')
        had_public=(self.root/'compose.public.yaml').is_file()
        had_push=(self.root/'compose.push.yaml').is_file()
        if not had_public:
            # Never replace an unrelated web server or container on this VPS.
            listeners=self.run(['ss','-H','-ltn'],capture=True)
            if any(re.search(r':(?:80|443)\s',line) for line in listeners.splitlines()):
                raise RuntimeError('Порты 80/443 заняты. Существующий веб-сервер сохранён, изменений нет.')
            ports=self.run(['docker','ps','--format','{{.Ports}}'],capture=True)
            if re.search(r':(?:80|443)->',ports):
                raise RuntimeError('Контейнер уже публикует порт 80/443. Изменений нет.')
        for name in ('nginx','runtime','acme','letsencrypt','work','certbot-logs'):
            directory=self.folder/name
            directory.mkdir(parents=True,exist_ok=True)
            os.chmod(directory,0o755 if name in ('nginx','runtime','acme') else 0o700)
        saved={}
        for p in [self.root/'compose.public.yaml',self.root/'compose.push.yaml',self.root/'push-public.env',
                  self.folder/'nginx'/'default.conf',self.folder/'nginx'/'proxy.inc',statefile]:
            saved[p]=p.read_bytes() if p.is_file() else None
        old_pointer=os.readlink(self.folder/'runtime'/'current') if (self.folder/'runtime'/'current').is_symlink() else None
        stage=self.folder/'compose.stage.json'
        atomic_write(stage,json.dumps(public_overlay(host),indent=2))
        app_changed=False
        try:
            self.message('Проверяем образы HTTPS и Certbot…')
            self.run(['docker','pull',NGINX_IMAGE]);self.run(['docker','pull',CERTBOT_IMAGE])
            self.run(['docker','run','--rm',CERTBOT_IMAGE,'--version'])
            atomic_write(self.folder/'nginx'/'proxy.inc',proxy_include(),0o644)
            if not had_public:
                atomic_write(self.folder/'nginx'/'default.conf',nginx_config(host,False),0o644)
                atomic_write(statefile,json.dumps({'host':host,'installed':False}))
            stage_command=compose(self.root,stage=stage)
            self.run(stage_command+['config','-q'])
            self.run(stage_command+['up','-d','--no-build','--no-deps','edge'])
            self.message('Проверяем владение адресом через Let’s Encrypt; приложение пока закрыто для HTTP…')
            self.certbot(certbot_arguments(host,is_ip,dry_run=True,email=email))
            self.certbot(certbot_arguments(host,is_ip,email=email))
            sync_certificate(self.folder)
            self.message('Сертификат получен. Включаем HTTPS и защищённые cookies…')
            app_changed=True
            self.run(stage_command+['up','-d','--no-build','--no-deps','api'])
            self.health()
            atomic_write(self.folder/'nginx'/'default.conf',nginx_config(host,True),0o644)
            self.run(stage_command+['exec','-T','edge','nginx','-t'])
            self.run(stage_command+['exec','-T','edge','nginx','-s','reload'])
            # nginx reload is asynchronous; the trusted TLS handshake must pass before push is enabled.
            for attempt in range(12):
                try:
                    self.tls_health(host);break
                except (RuntimeError,ValueError):
                    if attempt==11:raise
                    time.sleep(1)
            atomic_write(self.root/'compose.public.yaml',stage.read_text())
            push_source=source/'configure-push.sh'
            if not push_source.exists():
                push_source=source.parent/'api'/'configure-push.sh'
            self.run(['bash',str(push_source),f'https://{host}'])
            atomic_write(statefile,json.dumps({'host':host,'origin':f'https://{host}','installed':True,'is_ip':is_ip},indent=2))
            for name in ('access.py','setup-public.sh','renew-public.sh','status-public.sh','rollback-public.sh','configure-push.sh','compose.push.yaml'):
                destination=self.folder/name
                candidate=source/name
                if not candidate.exists() and name in ('configure-push.sh','compose.push.yaml'):
                    candidate=source.parent/'api'/name
                if candidate.resolve()!=destination.resolve():
                    shutil.copyfile(candidate,destination)
                os.chmod(destination,0o700 if destination.suffix!='.yaml' else 0o600)
            self.install_timer()
            self.message(f'Готово: https://{host}/ — вход под существующими логином и паролем.')
            self.message('На каждом телефоне: Настройки → Включить push. Затем проверьте новую заявку при свёрнутом браузере.')
        except Exception:
            self.message('Настройка не завершена. Возвращаем прежнюю конфигурацию приложения…')
            if not previous_state.get('installed'):
                self.run(['systemctl','disable','--now','liftcontrol-cert-renew.timer'],check=False)
            self.run(compose(self.root,stage=stage)+['stop','edge'],check=False)
            if not had_push:
                current=compose(self.root,stage=stage)
                self.run(current+['stop','push-worker'],check=False)
            for path,data in saved.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path,data.decode('utf-8'),0o644 if path.suffix in ('.conf','.inc') else 0o600)
            pointer=self.folder/'runtime'/'current'
            if old_pointer:
                pointer.unlink(missing_ok=True);pointer.symlink_to(old_pointer,target_is_directory=True)
            if app_changed:
                self.run(original+['up','-d','--no-build','--no-deps','api'],check=False)
            if had_public:
                self.run(original+['up','-d','--no-build','--no-deps','edge'],check=False)
            if had_push:
                self.run(original+['up','-d','--no-build','--no-deps','push-worker'],check=False)
            raise
        finally:
            stage.unlink(missing_ok=True)

    def install_timer(self):
        service='''[Unit]
Description=Renew LiftControl HTTPS certificate
After=docker.service network-online.target
Requires=docker.service
[Service]
Type=oneshot
WorkingDirectory=/opt/liftcontrol
ExecStart=/usr/bin/python3 /opt/liftcontrol/public/access.py renew
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
'''
        timer='''[Unit]
Description=Check LiftControl certificate every 6 hours
[Timer]
OnCalendar=*-*-* 00,06,12,18:17:00
RandomizedDelaySec=10m
Persistent=true
[Install]
WantedBy=timers.target
'''
        atomic_write(Path('/etc/systemd/system/liftcontrol-cert-renew.service'),service,0o644)
        atomic_write(Path('/etc/systemd/system/liftcontrol-cert-renew.timer'),timer,0o644)
        self.run(['systemctl','daemon-reload'])
        self.run(['systemctl','enable','--now','liftcontrol-cert-renew.timer'])

    def renew(self):
        state=json.loads((self.folder/'state.json').read_text())
        if not state.get('installed'):
            raise RuntimeError('HTTPS ещё не настроен.')
        pointer=self.folder/'runtime'/'current'
        previous=os.readlink(pointer) if pointer.is_symlink() else None
        try:
            self.certbot(['renew','--cert-name',CERTIFICATE_NAME,'--no-random-sleep-on-renew','--quiet'])
            sync_certificate(self.folder)
            current=compose(self.root)
            self.run(current+['exec','-T','edge','nginx','-t'])
            self.run(current+['exec','-T','edge','nginx','-s','reload'])
            self.tls_health(state['host'])
        except Exception:
            if previous:
                pointer.unlink(missing_ok=True);pointer.symlink_to(previous,target_is_directory=True)
            raise
        self.message('HTTPS_CERTIFICATE_CHECK_OK')

    def status(self):
        state=json.loads((self.folder/'state.json').read_text())
        self.tls_health(state['host'])
        self.message('HTTPS OK: '+state['origin'])
        output=self.run(['openssl','x509','-in',str(self.folder/'letsencrypt'/'live'/CERTIFICATE_NAME/'fullchain.pem'),'-noout','-enddate'],capture=True)
        self.message(output.strip())
        self.run(['systemctl','is-active','--quiet','liftcontrol-cert-renew.timer'])
        self.message('Автопродление: включено, проверка каждые 6 часов.')
        code="from core.push_notifications import push_config; from core.models import Organization,Elevator; import json; print(json.dumps({'push_configured':push_config()['enabled'],'organizations':[{'name':o.name,'elevators':Elevator.objects.filter(organization=o).count()} for o in Organization.objects.all()]},ensure_ascii=False))"
        output=self.run(compose(self.root)+['exec','-T','api','python','manage.py','shell','-c',code],capture=True)
        self.message(output.strip())
        worker=self.run(compose(self.root)+['ps','--status','running','--services'],capture=True)
        self.message('Отправитель push: '+('запущен' if 'push-worker' in worker.splitlines() else 'не запущен'))

    def rollback(self):
        # This is a configuration rollback only: application data and keys survive.
        current=compose(self.root)
        self.run(['systemctl','disable','--now','liftcontrol-cert-renew.timer'],check=False)
        self.run(current+['stop','edge'],check=False)
        (self.root/'compose.public.yaml').unlink(missing_ok=True)
        self.run(compose(self.root,public=False)+['up','-d','--no-build','--no-deps','api'])
        statefile=self.folder/'state.json'
        if statefile.exists():
            state=json.loads(statefile.read_text());state['installed']=False
            atomic_write(statefile,json.dumps(state))
        self.message('Публичный HTTPS отключён. Данные и ключи сохранены. Доступ к приложению — через прежний SSH-туннель.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','renew','status','rollback'])
    parser.add_argument('host',nargs='?')
    parser.add_argument('--email')
    args=parser.parse_args()
    if os.geteuid()!=0:
        parser.error('Запустите через sudo.')
    if args.action=='setup' and not args.host:
        parser.error('Укажите IPv4 или домен VPS.')
    if args.email and (len(args.email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',args.email)):
        parser.error('Некорректная почта.')
    access=Access()
    access.folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(access.folder,0o700)
    with open(access.folder/'.lock','a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error('Настройка или продление сертификата уже выполняется.')
        logpath=access.folder/'setup.log'
        with open(logpath,'a',encoding='utf-8') as log:
            os.chmod(logpath,0o600);access.log=log
            try:
                if args.action=='setup':access.setup(args.host,args.email)
                else:getattr(access,args.action)()
            except Exception as exc:
                access.message(str(exc))
                return 1
    return 0

if __name__=='__main__':
    raise SystemExit(main())
