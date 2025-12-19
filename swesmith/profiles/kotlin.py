import re

from dataclasses import dataclass, field
from swebench.harness.constants import TestStatus
from swesmith.constants import ENV_NAME
from swesmith.profiles.base import RepoProfile, registry


@dataclass
class KotlinProfile(RepoProfile):
    """
    Profile for Kotlin repositories.
    """

    exts: list[str] = field(default_factory=lambda: [".kt", ".java"])


@dataclass
class OkHttp8e0cc1b3(KotlinProfile):
    owner: str = "danielzayas"
    repo: str = "okhttp"
    commit: str = "8e0cc1b398a10c27a0921a14bc53ca770169d83c"
    # Broad test command; avoid container tests (Docker-in-Docker) during evaluation.
    # Resource caps help avoid OOM in constrained Docker environments.
    test_cmd: str = './gradlew test --no-daemon -Dorg.gradle.jvmargs="-Xmx8g -XX:MaxMetaspaceSize=1g" -x :container-tests:test'
    eval_sets: set[str] = field(
        default_factory=lambda: {"SWE-bench/SWE-bench_Multilingual"}
    )

    @property
    def dockerfile(self):
        # NOTE: SWE-smith targets linux/amd64 images; pin platform explicitly here.
        return f"""FROM --platform=linux/amd64 ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# OS-level deps + JDK 21
RUN apt-get update && apt-get install -y \\
    git curl wget unzip zip ca-certificates \\
    openjdk-21-jdk \\
    libstdc++6 zlib1g \\
    libc6-i386 lib32z1 lib32stdc++6 \\
  && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/{self.mirror_name} /{ENV_NAME}
WORKDIR /{ENV_NAME}

# Android SDK command-line tools
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV ANDROID_HOME=/opt/android-sdk
ENV PATH=$PATH:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools

RUN mkdir -p $ANDROID_SDK_ROOT/cmdline-tools && \\
    wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/cmdline.zip && \\
    unzip -q /tmp/cmdline.zip -d $ANDROID_SDK_ROOT/cmdline-tools && \\
    mv $ANDROID_SDK_ROOT/cmdline-tools/cmdline-tools $ANDROID_SDK_ROOT/cmdline-tools/latest && \\
    rm /tmp/cmdline.zip

# Pre-configure Android SDK location for Gradle
RUN echo "sdk.dir=$ANDROID_SDK_ROOT" > local.properties

# Accept licenses and install SDK packages needed by OkHttp build (compileSdk 35/36)
RUN yes | sdkmanager --licenses || true
RUN sdkmanager \\
    "platform-tools" \\
    "platforms;android-35" \\
    "platforms;android-36" \\
    "build-tools;35.0.0" \\
    "build-tools;36.0.0"

# Build (no tests) during image build for deterministic compile validation.
# Resource caps: helps avoid OOM in constrained Docker environments.
RUN chmod +x ./gradlew && ./gradlew clean assemble --no-daemon -Dorg.gradle.jvmargs="-Xmx8g -XX:MaxMetaspaceSize=1g" -x :container-tests:test
"""

    def log_parser(self, log: str) -> dict[str, str]:
        test_status_map = {}
        # Gradle test output patterns:
        # "Test okhttp3.CallTest > testExecution PASSED"
        # "okhttp3.CallTest > testExecution FAILED"
        # "Test okhttp3.CallTest.testExecution PASSED"
        patterns = [
            (r"Test\s+([^\s>]+)\s*>\s*([^\s]+)\s+(PASSED|FAILED)", r"\1.\2"),  # "Test Class > method STATUS"
            (r"([^\s>]+)\s*>\s*([^\s]+)\s+(PASSED|FAILED)", r"\1.\2"),  # "Class > method STATUS"
            (r"Test\s+([^\s.]+)\.([^\s]+)\s+(PASSED|FAILED)", r"\1.\2"),  # "Test Class.method STATUS"
        ]
        
        for line in log.split("\n"):
            line = line.strip()
            for pattern, name_template in patterns:
                match = re.search(pattern, line)
                if match:
                    # Build full test name from template
                    test_name = name_template
                    # Replace \1, \2 with match groups
                    if "\\1" in test_name:
                        test_name = test_name.replace("\\1", match.group(1))
                    if "\\2" in test_name:
                        test_name = test_name.replace("\\2", match.group(2))
                    
                    status = match.group(match.lastindex)  # Last group is always the status
                    if status == "PASSED":
                        test_status_map[test_name] = TestStatus.PASSED.value
                    elif status == "FAILED":
                        test_status_map[test_name] = TestStatus.FAILED.value
                    break
        return test_status_map


# Register all Kotlin profiles with the global registry
for name, obj in list(globals().items()):
    if (
        isinstance(obj, type)
        and issubclass(obj, KotlinProfile)
        and obj.__name__ != "KotlinProfile"
    ):
        registry.register_profile(obj)

