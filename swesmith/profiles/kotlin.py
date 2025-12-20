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
    test_cmd: str = './gradlew test --no-daemon -Dorg.gradle.jvmargs="-Xmx8g -XX:MaxMetaspaceSize=1g" -x :container-tests:test'
    eval_sets: set[str] = field(
        default_factory=lambda: {"SWE-bench/SWE-bench_Multilingual"}
    )

    @property
    def dockerfile(self):
        # Use the Kotlin/Android base image to avoid re-downloading JDK + Android SDK on every repo build.
        # TODO @john-b-yang: please push this kotlin base image to 'jyangballin/swesmith-kotlin-base'
        # because we'll want to use the ORG_NAME_DH_BASE_IMAGE or similar from `swesmith/constants.py`
        return f"""FROM --platform={self.pltf} danielzayas/swesmith-kotlin-base:latest

RUN git clone https://github.com/{self.mirror_name} /{ENV_NAME}
WORKDIR /{ENV_NAME}

# Gradle cache mount (BuildKit) to speed up iterative builds.
# Add --info/--stacktrace to make plugin-resolution failures diagnosable in build logs.
RUN --mount=type=cache,target=/root/.gradle \\
    chmod +x ./gradlew && \\
    ./gradlew clean assemble --no-daemon --info --stacktrace \\
      -Dorg.gradle.jvmargs="-Xmx8g -XX:MaxMetaspaceSize=1g" \\
      -x :container-tests:test
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

