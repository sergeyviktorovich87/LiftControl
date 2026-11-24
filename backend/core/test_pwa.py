import json
import struct
from django.test import SimpleTestCase


class PwaTests(SimpleTestCase):
    def test_public_manifest_and_icons(self):
        response = self.client.get('/manifest.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/manifest+json')
        manifest = json.loads(b''.join(response.streaming_content))
        self.assertEqual(manifest['start_url'], '/')
        self.assertEqual(manifest['scope'], '/')
        self.assertEqual(manifest['display'], 'standalone')
        for icon in manifest['icons']:
            result = self.client.get(icon['src'])
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result['Content-Type'], 'image/png')
            header = b''.join(result.streaming_content)
            self.assertEqual(header[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', header[16:24])
            self.assertEqual(f'{width}x{height}', icon['sizes'])

    def test_worker_is_public_root_scoped_and_keeps_push(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertEqual(response['Cache-Control'], 'no-cache')
        worker = b''.join(response.streaming_content)
        self.assertIn(b"addEventListener('push'", worker)
        self.assertIn(b"addEventListener('fetch'", worker)
        self.assertNotIn(b'caches.open', worker)

    def test_manifest_does_not_bypass_login(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertContains(self.client.get('/login/'), '/manifest.webmanifest')
