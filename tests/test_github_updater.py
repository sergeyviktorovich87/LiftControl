import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import subprocess
import zipfile

spec = importlib.util.spec_from_file_location('updater', Path(__file__).resolve().parents[1] / 'deploy/offline/github-updater.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class UpdaterTests(unittest.TestCase):
    def release(self, tag='v0.13.16', prerelease=False):
        name = f'LiftControl-{tag}-update.zip'
        return {'tag_name': tag, 'draft': False, 'prerelease': prerelease,
                'assets': [{'name': name + suffix, 'state': 'uploaded', 'size': 100}
                           for suffix in ('', '.sha256', '.intoto.jsonl')]}

    def test_versions_and_stable_channel(self):
        self.assertEqual(u.select_release(self.release(), '0.13.9')[0], '0.13.16')
        self.assertIsNone(u.select_release(self.release(), '0.13.16'))
        self.assertIsNone(u.select_release(self.release(), '0.13.17'))
        self.assertIsNone(u.select_release(self.release(prerelease=True), '0.13.15'))
        with self.assertRaises(ValueError):
            u.select_release(self.release('v0.13.16;bad'), '0.13.15')
        data = self.release()
        data['assets'].pop()
        with self.assertRaises(ValueError):
            u.select_release(data, '0.13.15')

    def package(self, directory, extra=None, corrupt=False):
        archive = directory / 'test.zip'
        files = {'VERSION.txt': b'0.13.16\n', 'SOURCE_COMMIT.txt': b'a'*40+b'\n',
                 'update-panel.sh': b'#!/bin/bash\n'}
        manifest = ''.join(f'{hashlib.sha256(body).hexdigest()}  {name}\n' for name, body in files.items())
        files['PATCH.sha256'] = manifest.encode()
        if corrupt:
            files['update-panel.sh'] += b'bad'
        with zipfile.ZipFile(archive, 'w') as z:
            for name, body in files.items():
                z.writestr('LiftControl-v0.13.16-update/' + name, body)
            if extra:
                z.writestr(extra, b'x')
        return archive

    def test_verified_archive(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            root = u.extract_checked(self.package(d), d, '0.13.16', 'a'*40)
            self.assertTrue((root / 'update-panel.sh').is_file())

    def test_zip_traversal_symlink_and_corruption(self):
        link = zipfile.ZipInfo('LiftControl-v0.13.16-update/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for extra, corrupt in [('LiftControl-v0.13.16-update/../escape', False),
                               ('/etc/escape', False), (link, False), (None, True)]:
            with self.subTest(extra=extra, corrupt=corrupt), tempfile.TemporaryDirectory() as t:
                d = Path(t)
                with self.assertRaises(ValueError):
                    u.extract_checked(self.package(d, extra, corrupt), d, '0.13.16', 'a'*40)

    def test_wrong_commit_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            with self.assertRaises(ValueError):
                u.extract_checked(self.package(d), d, '0.13.16', 'b'*40)

    def test_never_install_unsigned_or_changed_migrations(self):
        for bad_signature in (True, False):
            with self.subTest(bad_signature=bad_signature), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = self.package(root)
                archive_bytes = source.read_bytes()
                digest = hashlib.sha256(archive_bytes).hexdigest()
                name = 'LiftControl-v0.13.16-update.zip'
                called = []
                def fake_download(url, dest, limit):
                    dest.write_bytes((digest + '  ' + name + '\n').encode() if url.endswith('.sha256') else
                                     b'fixture' if url.endswith('.jsonl') else archive_bytes)
                def fake_run(args, **kw):
                    called.append(args[0])
                    if bad_signature:
                        raise subprocess.CalledProcessError(1, args)
                def fake_json(url, directory, filename):
                    return self.release() if filename == 'release.json' else {'sha': 'a'*40}
                with patch.multiple(u, STATE=root, health=lambda:'0.13.15', download=fake_download,
                                    get_json=fake_json, run=fake_run, migration_map=lambda directory:{'new.py':'x'},
                                    installed_migrations=lambda:{'old.py':'x'}):
                    if bad_signature:
                        with self.assertRaises(subprocess.CalledProcessError):
                            u.update()
                    else:
                        u.update()
                self.assertEqual(called, ['gh'])


if __name__ == '__main__':
    unittest.main()
