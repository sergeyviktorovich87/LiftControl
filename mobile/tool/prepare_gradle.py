"""Restore the pinned official distribution through its public asset API.

The ordinary GitHub release web redirect can return 504 while the public asset
API remains available. No credentials are needed or forwarded to the CDN.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
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
    # The Kotlin compiler is another large official asset whose web endpoint can
    # fail independently of Maven metadata. Seed Gradle's content-addressed store
    # only after verifying the publisher's SHA-256; normal POM resolution remains.
    compiler_sha = '9588fa696ac5507af764fd5660df6894185e12704ec1bc3f5cb772af4987f295'
    compiler = path.parent/'kotlin-compiler-embeddable-2.2.21.jar'
    if not compiler.is_file() or digest(compiler) != compiler_sha:
        subprocess.run(['curl','-fL','--retry','3','--retry-all-errors','--max-time','180',
            '-H','Accept: application/octet-stream','https://api.github.com/repos/JetBrains/kotlin/releases/assets/587847942','-o',str(compiler)],check=True)
    if digest(compiler) != compiler_sha:
        raise RuntimeError('KOTLIN_COMPILER_CHECKSUM_MISMATCH')
    with compiler.open('rb') as stream:
        artifact_hash = hashlib.file_digest(stream,'sha1').hexdigest()
    gradle_home = Path(os.environ.get('GRADLE_USER_HOME',str(Path.home()/'.gradle')))
    cached = gradle_home/'caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.21'/artifact_hash/compiler.name
    cached.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(compiler,cached)
    print('KOTLIN_COMPILER_VERIFIED '+compiler_sha)
    wrapper = Path(__file__).resolve().parents[1]/'android/gradle/wrapper/gradle-wrapper.properties'
    value = re.sub(r'^distributionUrl=.*$', lambda _: 'distributionUrl='+path.resolve().as_uri(),
        wrapper.read_text(), flags=re.MULTILINE)
    if 'distributionSha256Sum='+SHA256 not in value:
        raise RuntimeError('GRADLE_WRAPPER_CHECKSUM_MISMATCH')
    wrapper.write_text(value)
    print('GRADLE_DISTRIBUTION_VERIFIED '+SHA256)


if __name__ == '__main__':
    main()
