"""Restore pinned build tools from official sources, checking every byte.

Official distribution and Maven endpoints avoid anonymous GitHub API limits.
The public asset API remains a fallback. No credentials are forwarded to a CDN.
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


def download_verified(path, expected, urls):
    if path.is_file() and digest(path) == expected:
        return
    temporary = path.with_name(path.name + '.part')
    try:
        for url in urls:
            try:
                subprocess.run([
                    'curl', '-fL', '--retry', '2', '--connect-timeout', '20',
                    '--max-time', '180', '-H', 'Accept: application/octet-stream',
                    url, '-o', str(temporary),
                ], check=True)
            except subprocess.CalledProcessError:
                temporary.unlink(missing_ok=True)
                continue
            if digest(temporary) != expected:
                raise RuntimeError('BUILD_TOOL_CHECKSUM_MISMATCH: ' + path.name)
            temporary.replace(path)
            return
        raise RuntimeError('OFFICIAL_BUILD_TOOL_DOWNLOAD_FAILED: ' + path.name)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    path = Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())) / 'gradle-9.3.1-bin.zip'
    download_verified(path, SHA256, [
        'https://downloads.gradle.org/distributions/gradle-9.3.1-bin.zip', URL,
    ])
    if digest(path) != SHA256:
        raise RuntimeError('GRADLE_DISTRIBUTION_CHECKSUM_MISMATCH')
    local_maven = path.parent/'liftcontrol-verified-maven'
    compilers = [
        ('2.2.21',587847942,'9588fa696ac5507af764fd5660df6894185e12704ec1bc3f5cb772af4987f295','0b33c64f2622ba3bc8283378bdb7505f2be330a2275807038ad54359b33ddf9b'),
        ('2.4.0',587835542,'c2b25e8c1c93ec416ba4327f5e31eaec0f0c8847241b9353e294b8db9dce564f','f5d78540108e7bbc9162253ce52c42507ead2e530945213dd2a3b793b590c53c'),
    ]
    central = (
        'https://repo.maven.apache.org/maven2',
        'https://maven-central.storage-download.googleapis.com/maven2',
        'https://repo1.maven.org/maven2',
    )
    for version,asset_id,compiler_sha,pom_sha in compilers:
        artifact = f'org/jetbrains/kotlin/kotlin-compiler-embeddable/{version}/kotlin-compiler-embeddable-{version}'
        compiler = path.parent/f'kotlin-compiler-embeddable-{version}.jar'
        download_verified(compiler, compiler_sha, [
            *(f'{origin}/{artifact}.jar' for origin in central),
            f'https://api.github.com/repos/JetBrains/kotlin/releases/assets/{asset_id}',
        ])
        if digest(compiler) != compiler_sha:
            raise RuntimeError('KOTLIN_COMPILER_CHECKSUM_MISMATCH')
        pom = path.parent/f'kotlin-compiler-embeddable-{version}.pom'
        download_verified(pom, pom_sha, [f'{origin}/{artifact}.pom' for origin in central])
        if digest(pom) != pom_sha:
            raise RuntimeError('KOTLIN_POM_CHECKSUM_MISMATCH')
        module = local_maven/f'org/jetbrains/kotlin/kotlin-compiler-embeddable/{version}'
        module.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(compiler,module/compiler.name)
        shutil.copyfile(pom,module/pom.name)
        print('KOTLIN_COMPILER_VERIFIED '+version+' '+compiler_sha)
    gradle_home = Path(os.environ.get('GRADLE_USER_HOME',str(path.parent/'liftcontrol-gradle-home')))
    gradle_home.mkdir(mode=0o700,parents=True,exist_ok=True)
    old_properties = Path.home()/'.gradle/gradle.properties'
    properties = gradle_home/'gradle.properties'
    settings = old_properties.read_text() if old_properties.is_file() and old_properties.resolve()!=properties.resolve() else ''
    properties.write_text(settings+'\norg.gradle.jvmargs=-Xmx3g -XX:MaxMetaspaceSize=1g -XX:ReservedCodeCacheSize=256m\norg.gradle.workers.max=2\nkotlin.compiler.execution.strategy=in-process\n')
    properties.chmod(0o600)
    init = gradle_home/'init.d/liftcontrol-verified-compiler.init.gradle'
    init.parent.mkdir(parents=True,exist_ok=True)
    init.write_text("""def modes = [:]
def verifiedRepository = { repositories ->
    repositories.exclusiveContent {
        forRepository {
            repositories.maven {
                name = 'LiftControlVerifiedCompiler'
                url = new File(System.getenv('LIFTCONTROL_PINNED_MAVEN')).toURI()
                metadataSources { mavenPom(); artifact() }
            }
        }
        filter {
            includeVersion('org.jetbrains.kotlin','kotlin-compiler-embeddable','2.2.21')
            includeVersion('org.jetbrains.kotlin','kotlin-compiler-embeddable','2.4.0')
        }
    }
}
gradle.settingsEvaluated { settings ->
    modes[settings.gradle] = settings.dependencyResolutionManagement.repositoriesMode.get().name() == 'PREFER_PROJECT'
    verifiedRepository(settings.dependencyResolutionManagement.repositories)
}
gradle.beforeProject { project ->
    if (modes[project.gradle]) verifiedRepository(project.repositories)
}
""")
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a') as env:
            env.write('GRADLE_USER_HOME='+str(gradle_home)+'\n')
            env.write('LIFTCONTROL_PINNED_MAVEN='+str(local_maven)+'\n')
    wrapper = Path(__file__).resolve().parents[1]/'android/gradle/wrapper/gradle-wrapper.properties'
    value = re.sub(r'^distributionUrl=.*$', lambda _: 'distributionUrl='+path.resolve().as_uri(),
        wrapper.read_text(), flags=re.MULTILINE)
    if 'distributionSha256Sum='+SHA256 not in value:
        raise RuntimeError('GRADLE_WRAPPER_CHECKSUM_MISMATCH')
    wrapper.write_text(value)
    print('GRADLE_DISTRIBUTION_VERIFIED '+SHA256)


if __name__ == '__main__':
    main()
