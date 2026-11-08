"""Restore the pinned official distribution through its public asset API.

The ordinary GitHub release web redirect can return 504 while the public asset
API remains available. No credentials are needed or forwarded to the CDN.
"""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

SHA256 = 'b266d5ff6b90eada6dc3b20cb090e3731302e553a27c5d3e4df1f0d76beaff06'
URL = 'https://api.github.com/repos/gradle/gradle-distributions/releases/assets/347704202'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    path = Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())) / 'gradle-9.3.1-bin.zip'
    if not path.is_file() or digest(path) != SHA256:
        subprocess.run(['curl','-fL','--retry','3','--retry-all-errors','--max-time','180',
            '-H','Accept: application/octet-stream',URL,'-o',str(path)],check=True)
    if digest(path) != SHA256:
        raise RuntimeError('GRADLE_DISTRIBUTION_CHECKSUM_MISMATCH')
    wrapper = Path(__file__).resolve().parents[1]/'android/gradle/wrapper/gradle-wrapper.properties'
    value = re.sub(r'^distributionUrl=.*$', lambda _: 'distributionUrl='+path.resolve().as_uri(),
        wrapper.read_text(), flags=re.MULTILINE)
    if 'distributionSha256Sum='+SHA256 not in value:
        raise RuntimeError('GRADLE_WRAPPER_CHECKSUM_MISMATCH')
    wrapper.write_text(value)
    print('GRADLE_DISTRIBUTION_VERIFIED '+SHA256)


if __name__ == '__main__':
    main()
