"""Real Docker/Nginx/Django TLS, login and CSRF check with an ephemeral test CA."""
import http.cookiejar
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

spec=importlib.util.spec_from_file_location('public_access',Path(__file__).with_name('access.py'))
access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)


def run(args,input=None):
    result=subprocess.run(args,text=True,input=input,capture_output=True)
    if result.returncode:
        # No test password, session cookie or private key is part of the command line or output.
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout


def main():
    with tempfile.TemporaryDirectory(prefix='liftcontrol-https-test-') as temp:
        root=Path(temp)
        for path in [root/'public'/'nginx',root/'public'/'runtime'/'current',root/'public'/'acme'/'.well-known'/'acme-challenge']:
            path.mkdir(parents=True,exist_ok=True,mode=0o755)
        key=root/'public'/'runtime'/'current'/'privkey.pem'
        certificate=key.with_name('fullchain.pem')
        run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=localhost',
             '-addext','subjectAltName=DNS:localhost','-days','1','-keyout',str(key),'-out',str(certificate)])
        trust=root/'test-ca.pem';shutil.copyfile(certificate,trust)
        # Match production UID and key mode using this isolated fixture, not a real host key.
        run(['docker','run','--rm','--network','none','--user','0:0','--cap-drop','ALL',
             '--cap-add','CHOWN','--cap-add','FOWNER','--entrypoint','sh',
             '-v',f'{key.parent}:/work',access.NGINX_IMAGE,'-c',
             'chown 101:101 /work/fullchain.pem /work/privkey.pem; chmod 400 /work/fullchain.pem /work/privkey.pem'])
        (root/'public'/'nginx'/'default.conf').write_text(access.nginx_config('localhost',True))
        (root/'public'/'nginx'/'proxy.inc').write_text(access.proxy_include())
        probe=root/'public'/'acme'/'.well-known'/'acme-challenge'/'probe'
        probe.write_text('challenge-path-ok')
        config=access.public_overlay('localhost')
        config['services']['api'].update({'image':'liftcontrol-api:public-test','read_only':True,
           'tmpfs':['/tmp:size=64m,mode=1777'],'networks':['frontend'],
           'cap_drop':['ALL'],'security_opt':['no-new-privileges:true']})
        config['services']['api']['environment'].update({'DJANGO_DEBUG':'True','DB_ENGINE':'sqlite',
           'DJANGO_SQLITE_PATH':'/tmp/public-test.sqlite3','DJANGO_SETTINGS_MODULE':'liftcontrol.settings'})
        config['services']['edge']['ports']=['127.0.0.1:18082:8080','127.0.0.1:18443:8443']
        config['networks']={'frontend':{'driver':'bridge'}}
        composefile=root/'compose.json';composefile.write_text(json.dumps(config))
        command=['docker','compose','-p','liftcontrol-https-smoke','-f',str(composefile)]
        try:
            run(command+['config','-q'])
            run(command+['up','-d','api','edge'])
            run(command+['exec','-T','api','python','manage.py','migrate','--noinput'])
            password=secrets.token_urlsafe(24)
            code="import django,json,sys;django.setup();from django.contrib.auth import get_user_model;d=json.load(sys.stdin);get_user_model().objects.create_superuser('tls-test',password=d['password'])"
            run(command+['exec','-T','api','python','-c',code],json.dumps({'password':password}))
            ctx=ssl.create_default_context(cafile=str(trust))
            for attempt in range(40):
                try:
                    with urllib.request.urlopen('https://localhost:18443/api/health/',context=ctx,timeout=2) as response:
                        assert json.load(response)['version']=='0.6'
                    break
                except (OSError,ValueError):time.sleep(.25)
            else:raise RuntimeError('TLS health did not become ready')
            with urllib.request.urlopen('http://127.0.0.1:18082/.well-known/acme-challenge/probe') as response:
                assert response.read()==b'challenge-path-ok'
            jar=http.cookiejar.CookieJar()
            browser=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),urllib.request.HTTPSHandler(context=ctx))
            with browser.open('https://localhost:18443/login/') as response:html=response.read().decode()
            token=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',html).group(1)
            origin='https://localhost:18443'
            form=urllib.parse.urlencode({'csrfmiddlewaretoken':token,'username':'tls-test','password':password,'next':'/'}).encode()
            with browser.open(urllib.request.Request(origin+'/login/',data=form,headers={'Origin':origin})) as response:
                assert response.status==200
            cookies={cookie.name:cookie for cookie in jar}
            assert cookies['sessionid'].secure and cookies['csrftoken'].secure
            with browser.open(urllib.request.Request(origin+'/api/me/',headers={'X-Forwarded-Proto':'http'})) as response:
                profile=json.load(response)
            assert profile['role']=='ADMIN'
            headers={'Origin':origin,'Content-Type':'application/json','X-CSRFToken':profile['csrf'],'X-Forwarded-Proto':'http'}
            with browser.open(urllib.request.Request(origin+'/api/chat/',data=b'{"body":"TLS integration check"}',headers=headers)) as response:
                assert response.status==201
            headers['Origin']='https://evil.invalid'
            try:
                browser.open(urllib.request.Request(origin+'/api/chat/',data=b'{"body":"Blocked"}',headers=headers))
                raise AssertionError('Foreign origin unexpectedly accepted')
            except urllib.error.HTTPError as exc:
                assert exc.code==403
            try:
                urllib.request.urlopen(urllib.request.Request(origin+'/api/health/',headers={'Host':'evil.invalid'}),context=ctx)
                raise AssertionError('Foreign host unexpectedly accepted')
            except (urllib.error.URLError,OSError):pass
            run(command+['exec','-T','edge','nginx','-t'])
            run(command+['exec','-T','edge','nginx','-s','reload'])
            print('HTTPS_SMOKE_OK: TLS verified, real Django login, Secure cookies, same-origin CSRF, foreign origin/host blocked, ACME webroot, reload.')
        except Exception:
            logs=run(command+['logs','--no-color','--tail','70'])
            print(logs)
            raise
        finally:
            run(command+['down','-v','--remove-orphans'])

if __name__=='__main__':main()
