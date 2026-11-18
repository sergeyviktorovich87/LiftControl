import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from prepare_gradle import download_verified


class VerifiedDownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'tool.zip'
        self.data = b'expected official build tool'
        self.sha = hashlib.sha256(self.data).hexdigest()

    def write_download(self, command, **kwargs):
        Path(command[-1]).write_bytes(self.data)

    @patch('prepare_gradle.subprocess.run')
    def test_verified_local_file_needs_no_network(self, run):
        self.path.write_bytes(self.data)
        download_verified(self.path, self.sha, ['https://official.example/tool'])
        run.assert_not_called()

    @patch('prepare_gradle.subprocess.run')
    def test_network_failure_uses_official_fallback(self, run):
        def download(command, **kwargs):
            if command[-3] == 'https://primary.example/tool':
                Path(command[-1]).write_bytes(b'partial failed response')
                raise subprocess.CalledProcessError(22, command)
            self.write_download(command, **kwargs)

        run.side_effect = download
        download_verified(self.path, self.sha, [
            'https://primary.example/tool', 'https://fallback.example/tool',
        ])
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertEqual(run.call_count, 2)
        self.assertFalse(self.path.with_suffix('.zip.part').exists())

    @patch('prepare_gradle.subprocess.run')
    def test_checksum_mismatch_stops_without_replacing_existing_file(self, run):
        self.path.write_bytes(b'existing bytes')
        run.side_effect = lambda command, **kwargs: Path(command[-1]).write_bytes(b'wrong archive')
        with self.assertRaisesRegex(RuntimeError, 'CHECKSUM_MISMATCH'):
            download_verified(self.path, self.sha, [
                'https://primary.example/tool', 'https://fallback.example/tool',
            ])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.path.read_bytes(), b'existing bytes')
        self.assertFalse(self.path.with_suffix('.zip.part').exists())

    @patch('prepare_gradle.subprocess.run')
    def test_all_download_failures_leave_no_partial_artifact(self, run):
        run.side_effect = subprocess.CalledProcessError(22, ['curl'])
        with self.assertRaisesRegex(RuntimeError, 'OFFICIAL_BUILD_TOOL_DOWNLOAD_FAILED'):
            download_verified(self.path, self.sha, ['https://official.example/tool'])
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_suffix('.zip.part').exists())


if __name__ == '__main__':
    unittest.main()
