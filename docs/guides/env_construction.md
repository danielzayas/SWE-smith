SWE-smith enables automatic construction of execution environments for repositories.
We'll review the two steps of this process:

1. SWE-agent + LM attempts to install a repository + run the testing suite.
2. Construct an execution environment (Docker image).

For this section, we'll use the [Instagram/MonkeyType](https://github.com/Instagram/MonkeyType/) repository as a running example, 
specifically at commit [`70c3acf`](https://github.com/Instagram/MonkeyType/tree/70c3acf62950be5dfb28743c7a719bfdecebcd84).

## Automatically Install Repos with SWE-agent

Coming soon!

### Non-Python Languages

Profiles exist for JavaScript, Rust, Java, etc., but there is no `try_install_*` installer/exporter for them. The `create_images` entrypoint can still build images for non-Python repos as long as a profile class with a Dockerfile is registered, but installs happen only inside that Dockerfile during the image build (no pre-exported env YAML/SH like Python). To onboard a new non-Python repo you currently need to add a profile with its own Dockerfile/install steps; there is no automated install/export helper yet.

## Create an Execution Environment
First, create the conda environment for the target repository.
```bash
python -m swesmith.build_repo.try_install_py Instagram/MonkeyType install_repo.sh \
    --commit 70c3acf62950be5dfb28743c7a719bfdecebcd84
```
where `install_repo.sh` is the script that installs the repository.
([Example](https://github.com/SWE-bench/SWE-smith/blob/main/configs/install_repo.sh))

If successful, two artifacts will be produced under `logs/build_repo/records/`:
* `sweenv_[repo + commit].yml`: A dump of the conda environment that was created.
* `sweenv_[repo + commit].sh`: A log of the installation process.

Next, run the following command to create a Docker image for the repository.

```bash
python -m swesmith.build_repo.create_images --repos Instagram/MonkeyType
```

Alternatively, `create_images.py` is the entrypoint for building (and optionally pushing) environment images from the registered `RepoProfile` set:

```shell
python -m swesmith.build_repo.create_images --profiles Instagram/MonkeyType --push
```

This command will create two artifacts:
1. A mirror of the original repository at the specified commit, created under [`swesmith`](https://github.com/orgs/swesmith/repositories). To change the organization, you can...
    * Pass in an `--org` argument, or
    * (If built from source) Change `ORG_NAME_GH` in `swesmith/constants.py`
2. A Docker image (`swesmith.x86_64.<repo>.<commit>`) which contains the installed codebase.

It's good practice to check that your Docker image works as expected.
```bash
docker run -it --rm swesmith.x86_64.instagram__monkeytype.70c3acf6
```
Within the container, run the testing suite (e.g. `pytest`) to ensure that the codebase is functioning as expected.

!!! note "Get existing Docker images"

    All repositories represented in the SWE-smith [dataset](https://huggingface.co/datasets/SWE-bench/SWE-smith) are available to download. Simply run:
    ```bash
    python -m swesmith.build_repo.download_images
    ```

## What goes into the image: OS-level deps vs env deps

When SWE-smith builds an environment image for a repo, it may install dependencies in **two different places**:

- **Inside the Python/conda environment**: typical `pip install ...` / `conda install ...` packages that live in the exported `sweenv_*.yml`.
- **At the container OS layer**: apt packages and other system tooling installed during the Docker build. These tools are *not* “in the Python env”, but are available to it at runtime.

This distinction matters because some repos need **system binaries or headers** that pip/conda alone can’t provide, for example:

- **Ghostscript** for PDF parsing (e.g. `pdfplumber`)
- **Graphviz CLI** for tests that render dependency graphs (e.g. `pipdeptree`)
- **System headers/libraries** for building native deps (e.g. `libxml2-dev`, `libxslt-dev`, `libjpeg-dev` as seen in `scrapy`)
- **Java toolchain** for repos that need it during builds/tests/docs (e.g. `openjdk-17-*` as seen in `hydra`)
- **Build toolchains** (gcc/cmake/meson/ninja/...) for projects like `conan`

In SWE-smith, these OS-level installs are typically expressed in a repo profile’s `install_cmds` as `apt-get ...` lines alongside the `pip install ...` lines.

## How repo profiles drive Docker builds (and why OS deps get reused)

Each `RepoProfile` supplies a list of shell commands (`install_cmds`) that become the **setup script** executed during the Docker build for that image (e.g., cloning the mirrored repo, then running the profile’s install steps).

Because `apt-get` runs during the Docker build, system packages land in the **image filesystem**, not in the exported conda/pip environment. That means:

- **They’re reused automatically** every time you run a container from that same image tag.
- **They won’t appear** in `sweenv_*.yml` exports (those capture the env, not the OS layer).

If you see runtime failures like “missing `gs`/`dot`/headers”, check whether the repo’s profile needs extra OS dependencies in its `install_cmds`.

## Image naming, commit alignment, and “reuse” behavior

SWE-smith intentionally builds images **pinned to a specific upstream commit**:

- The profile pins an upstream commit.
- That commit hash is baked into:
  - the mirrored repo name, and
  - the Docker image tag.

Practically, this means images are **per repo + per commit** (e.g. `swesmith.x86_64.<repo>.<commit>`), not a single “rolling” image shared across many commits. This design favors deterministic, reproducible builds and avoids having to guess which historical commits can safely share an environment.

Related: when reproducing bugs from PRs, SWE-smith often applies a patch (including “reversal patches” when a PR was merged) **on top of the mirrored commit’s environment**, rather than checking out the PR’s original historical base commit. The environment corresponds to the profile’s pinned commit; the patch adjusts repo content to match the target bug state.

## Appendix: Missing Python Dependency Root Cause Analysis & Fix

### Problem
The eval for `python-openxml__python-docx.0cf6d71f.combine_module__j1zdp70p` failed because the built Docker image’s `testbed` environment lacked the `pyparsing` dependency. Pytest aborted during collection before any tests ran. The yamllint task succeeded; the python-docx task did not.

- `try_install_py` was run inside a linux/x86_64 Miniconda container to export `sweenv_python-openxml__python-docx.0cf6d71f.yml`. `try_install_py` behavior succeeded even when downstream tests would fail due to missing deps.
- `create_images.py` consumed that env file and built `danielzayas/swesmith.x86_64.python-openxml_1776_python-docx.0cf6d71f`.
- During gold eval, pytest failed on import: `ModuleNotFoundError: No module named 'pyparsing'` (reproduced inside the image with `pytest -vv --maxfail=1 tests/parts/test_story.py::DescribeStoryPart::it_can_create_a_new_pic_inline`).
- The env YAML did not include `pyparsing`, so the image did not either.

### Root cause
The installation recipe used by `try_install_py` (`configs/install_repo.sh`: `pip install -e .` then `pip install pytest`) does not install repo-specific test/dev dependencies. For `python-docx`, tests require `pyparsing`, but it is not installed because:
- It is not in the minimal install script.
- It is not added via profile-specific `install_cmds`.
- Exported env therefore omits `pyparsing`, and the image inherits that omission.

Branch state is not at fault: the gold patch applied cleanly and tests were reverted; the failure was missing deps.

### Fix 

Fail fast if imports/deps are missing:
1) Install test/dev deps during env export (done)
   - `configs/install_repo.sh` now tries `pip install -e .[test]`, falls back to `requirements-test.txt`, supports profile hooks, and accepts extra test deps. It honors `SWESMITH_PYTHON_VERSION`.
2) Add a smoke-test gate to `try_install_py` (done)
   - After install, `pytest -q --maxfail=1` (or provided smoke cmd) runs inside the env; failures abort export.
3) Re-export envs on linux/x86_64 (done for this instance)
   - Env/artifacts live under `logs/build_images/env/<repo>.<commit>/`.
4) Rebuild and push images from the validated envs (done)
   - Image rebuilt/pushed: `danielzayas/swesmith.x86_64.python-openxml_1776_python-docx.0cf6d71f` (timestamp reflects rebuilt run).


### Test Plan

Env re-exported, image rebuilt/pushed, and the gold eval now resolves the task:

```shell
(venv) danielzayas ~/Development/SWE-bench/SWE-smith [main] $ python -m swesmith.harness.eval \
  --run_id retry-python-docx-j1zdp70p \
  --redo_existing \
  -i "python-openxml__python-docx.0cf6d71f.combine_module__j1zdp70p" \
  --predictions_path gold \
  --dataset_path logs/run_evaluation/two_instances_local.json \
  --workers 1

Using gold predictions for eval (ignoring `predictions_path` argument)
Evaluation: 100%|████████████████████████████████████████████████████████████████████████████████| 1/1 [00:21<00:00, 21.20s/it, ✓=1, ✖=0, timeout=0, error=0]
All instances run.
Resolved 1/1 instances.
Wrote report to logs/run_evaluation/retry-python-docx-j1zdp70p/report.json
```
