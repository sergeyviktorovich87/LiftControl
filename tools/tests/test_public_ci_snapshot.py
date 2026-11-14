"""Tests for safe public-only CI snapshot export."""
import tempfile
import unittest
import json
from pathlib import Path

from tools.public_ci_snapshot import export, sanitized, allowed


class PublicSnapshotTests(unittest.TestCase):
    def make_checkout(self, base):
        root=base/'private-source'
        (root/'backend/core').mkdir(parents=True)
        (root/'backend/manage.py').write_text("print('sample')\n",encoding='utf-8')
        for number in range(45):
            (root/'backend/core'/f'example_{number}.py').write_text(
                "safe = True\n",encoding='utf-8')
        return root

    def approve(self, root):
        allowed_paths=sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob('*')
            if path.is_file() and allowed(path.relative_to(root))
        )
        (root/'tools').mkdir(exist_ok=True)
        (root/'tools/public_ci_allowlist.json').write_text(
            json.dumps({'schema':1, 'files':allowed_paths}),
            encoding='utf-8',
        )

    def test_redacts_real_fixture_labels(self):
        result=sanitized(
            "'Мегаполис' 'Эверест' 'Александр Николаи' "
            "'Игнатьевское шоссе' 'Воронкова' 'Чайка Smart'",
            Path('web/src/demo.js'))
        self.assertNotIn('Мегаполис',result)
        self.assertNotIn('Николаи',result)
        self.assertNotIn('Игнатьевское',result)
        self.assertIn('Организация Альфа',result)
        self.assertIn('Иванов',result)

    def test_denies_live_key_pattern_and_nonlocal_ip(self):
        with self.assertRaisesRegex(ValueError,'credential'):
            sanitized("token = 'ghp_" + "A"*35 + "'",
                Path('backend/core/bad.py'))
        with self.assertRaisesRegex(ValueError,'network address'):
            sanitized("server = '203.0.113.13'",
                Path('backend/core/bad.py'))

    def test_omits_original_fixtures_and_release_keys(self):
        for text in (
            'backend/core/megapolis_data.py',
            'backend/core/management/commands/import_megapolis.py',
            'backend/.env.example',
            'mobile/android/app/google-services.json',
            'mobile/android/secret.jks',
            'mobile/build/app-release.apk',
            '.github/workflows/android-sign-release.yml',
            'deploy/api/compose.api.yaml',
        ):
            self.assertFalse(allowed(Path(text)), text)
        self.assertTrue(allowed(Path('backend/core/views.py')))
        self.assertTrue(allowed(Path('mobile/lib/main.dart')))

    def test_strips_real_customer_import_tests(self):
        result=sanitized(
            "class SafeTests(TestCase):\n    pass\n\n"
            "class MegapolisImportTests(TestCase):\n    pass\n",
            Path('backend/core/tests_organizations.py'))
        self.assertIn('SafeTests',result)
        self.assertNotIn('MegapolisImportTests',result)

    def test_snapshot_copies_no_history_and_generates_ci(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=self.make_checkout(base)
            (root/'.git').mkdir()
            (root/'.git/config').write_text('private repository',encoding='utf-8')
            (root/'backend/core/megapolis_data.py').write_text(
                'real customer records',encoding='utf-8')
            (root/'mobile/lib/core').mkdir(parents=True)
            (root/'mobile/lib/core/demo.dart').write_text(
                "name='Эверест'\n",encoding='utf-8')
            self.approve(root)
            output=base/'public-ci'
            count=export(root,output)
            self.assertGreaterEqual(count,40)
            self.assertFalse((output/'.git').exists())
            self.assertFalse((output/'backend/core/megapolis_data.py').exists())
            self.assertIn('Организация Бета',
                (output/'mobile/lib/core/demo.dart').read_text('utf-8'))
            self.assertIn('workflow_dispatch',
                (output/'.github/workflows/public-ci.yml').read_text('utf-8'))
            self.assertTrue((output/'PUBLIC_SNAPSHOT_MANIFEST.json').is_file())

    def test_public_allowlist_rejects_new_unreviewed_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=self.make_checkout(base)
            self.approve(root)
            (root/'backend/core/unreviewed.py').write_text('new=True',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'allowlist'):
                export(root,base/'public-ci')

    def test_failed_scan_does_not_write_any_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            root=self.make_checkout(base)
            (root/'backend/core/example_0.py').write_text(
                "token='ghp_" + "A"*36 + "'",encoding='utf-8')
            self.approve(root)
            dest=base/'public-ci'
            with self.assertRaises(ValueError):
                export(root,dest)
            self.assertFalse(dest.exists())


if __name__=='__main__':
    unittest.main()
