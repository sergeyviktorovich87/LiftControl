"""Configuration, secret-handling and preflight regressions; no production server access."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('public_access',Path(__file__).with_name('access.py'))
access=importlib.util.module_from_spec(spec);spec.loader.exec_module(access)


class PublicAccessTests(unittest.TestCase):
    def test_public_ipv4_domain_and_idna(self):
        self.assertEqual(access.normalize_host('89.169.20.154'),('89.169.20.154',True))
        self.assertEqual(access.normalize_host('Lift.Example.Com.'),('lift.example.com',False))
        self.assertTrue(access.normalize_host('лифт.рф')[0].startswith('xn--'))

    def test_rejects_private_ip_invalid_host_and_config_injection(self):
        for host in ['127.0.0.1','192.168.1.1','0.0.0.0','169.254.169.254','::1','localhost','fake.local',
                     'https://lift.example.com','1.2.3.999','a..example.com','a.example.com/path',
                     'a.example.com;include /etc/passwd','a.example.com\nserver{}','a.example.com$host',
                     'a.example.com:443','user@a.example.com','-bad.example.com','a.example.com#x']:
            with self.subTest(host=host),self.assertRaises(ValueError):access.normalize_host(host)

    def test_initial_http_server_never_proxies_the_application(self):
        text=access.nginx_config('89.169.20.154',False)
        self.assertIn('return 503',text)
        self.assertIn('/.well-known/acme-challenge/',text)
        self.assertNotIn('proxy_pass',text)
        self.assertNotIn('listen 8443',text)

    def test_secure_proxy_rejects_foreign_host_and_overwrites_forwarded_headers(self):
        text=access.nginx_config('89.169.20.154',True)
        self.assertIn('if ($host != "89.169.20.154") { return 444; }',text)
        self.assertIn('limit_req zone=liftcontrol_login',text)
        self.assertIn('POST $binary_remote_addr',text)
        headers=access.proxy_include()
        self.assertIn('proxy_set_header X-Forwarded-Proto https;',headers)
        self.assertIn('proxy_set_header X-Forwarded-For $remote_addr;',headers)
        self.assertNotIn('$http_x_forwarded_proto',headers)
        self.assertNotIn('$request_body',text)
        self.assertNotIn('$request_uri\' ',text)

    def test_public_compose_keeps_database_private_and_nginx_unprivileged(self):
        config=access.public_overlay('89.169.20.154')
        self.assertNotIn('db',config['services'])
        self.assertNotIn('ports',config['services']['api'])
        edge=config['services']['edge']
        self.assertEqual(edge['networks'],['frontend'])
        self.assertEqual(edge['user'],'101:101')
        self.assertEqual(edge['cap_drop'],['ALL'])
        self.assertTrue(edge['read_only'])
        self.assertTrue(config['services']['api']['environment']['DJANGO_BEHIND_HTTPS_PROXY'])

    def test_ip_certificate_requires_shortlived_profile_and_real_output_is_separate(self):
        args=access.certbot_arguments('89.169.20.154',True)
        self.assertEqual(args[args.index('--ip-address')+1],'89.169.20.154')
        self.assertEqual(args[args.index('--required-profile')+1],'shortlived')
        self.assertNotIn('--staging',args)
        self.assertNotIn('--dry-run',args)
        self.assertIn('--dry-run',access.certbot_arguments('89.169.20.154',True,dry_run=True))
        self.assertNotIn('--keep-until-expiring',access.certbot_arguments('89.169.20.154',True,dry_run=True))
        self.assertIn('-d',access.certbot_arguments('lift.example.com',False))

    def test_key_is_private_and_missing_new_pair_preserves_current_pair(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(access.os,'chown'):
            folder=Path(tmp);source=folder/'letsencrypt'/'live'/access.CERTIFICATE_NAME
            source.mkdir(parents=True)
            (source/'fullchain.pem').write_text('fake certificate for test only')
            (source/'privkey.pem').write_text('fake private key for test only')
            access.sync_certificate(folder)
            target=folder/'runtime'/'current'
            previous=os.readlink(target)
            self.assertEqual((target/'privkey.pem').stat().st_mode&0o777,0o400)
            self.assertEqual(target.resolve().stat().st_mode&0o777,0o700)
            (source/'privkey.pem').unlink()
            with self.assertRaises(RuntimeError):access.sync_certificate(folder)
            self.assertEqual(os.readlink(target),previous)

    def test_busy_public_port_does_not_change_existing_deployment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('compose.yaml','compose.api.yaml','compose.v04.yaml','compose.v06.yaml'):(root/name).write_text('{}')
            obj=access.Access(root)
            def response(args,**kwargs):
                return 'LISTEN 0 128 0.0.0.0:443 0.0.0.0:*' if args[:2]==['ss','-H'] else ''
            with patch.object(obj,'health'),patch.object(obj,'run',side_effect=response):
                with self.assertRaisesRegex(RuntimeError,'80/443'):obj.setup('89.169.20.154')
            self.assertFalse((root/'compose.public.yaml').exists())
            self.assertEqual((root/'compose.v06.yaml').read_text(),'{}')
            self.assertFalse((root/'public').exists())

    def test_repeat_composition_retains_public_and_push_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('compose.yaml','compose.api.yaml','compose.v06.yaml','compose.push.yaml','compose.public.yaml'):(root/name).touch()
            result=access.compose(root)
            self.assertIn(str(root/'compose.push.yaml'),result)
            self.assertEqual(result[-1],str(root/'compose.public.yaml'))
            self.assertNotIn(str(root/'compose.public.yaml'),access.compose(root,public=False))

if __name__=='__main__':unittest.main()
