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
## Root Cause Analysis: Missing `pyparsing` in `python-openxml__python-docx.0cf6d71f.combine_module__j1zdp70p`

### Summary
The eval for `python-openxml__python-docx.0cf6d71f.combine_module__j1zdp70p` failed because the built Docker image’s `testbed` environment lacked the `pyparsing` dependency. Pytest aborted during collection before any tests ran. The yamllint task succeeded; the python-docx task did not.

### What happened (evidence)
- `try_install_py` was run inside a linux/x86_64 Miniconda container to export `sweenv_python-openxml__python-docx.0cf6d71f.yml`.
- `create_images.py` consumed that env file and built `danielzayas/swesmith.x86_64.python-openxml_1776_python-docx.0cf6d71f`.
- During gold eval, pytest failed on import: `ModuleNotFoundError: No module named 'pyparsing'` (reproduced inside the image with `pytest -vv --maxfail=1 tests/parts/test_story.py::DescribeStoryPart::it_can_create_a_new_pic_inline`).
- The env YAML did not include `pyparsing`, so the image did not either.

### Root cause
The installation recipe used by `try_install_py` (`configs/install_repo.sh`: `pip install -e .` then `pip install pytest`) does not install repo-specific test/dev dependencies. For `python-docx`, tests require `pyparsing`, but it is not installed because:
- It is not in the minimal install script.
- It is not added via profile-specific `install_cmds`.
- Exported env therefore omits `pyparsing`, and the image inherits that omission.

Branch state is not at fault: the gold patch applied cleanly and tests were reverted; the failure was missing deps.

### Clarifications
- Where `install_repo.sh` is used: `try_install_py.py` runs `. {install_script}` (e.g., `configs/install_repo.sh`) right after cloning and before exporting `sweenv_*.yml`. Whatever that script installs is what gets captured in the env file.
- Python version pin: `configs/install_repo.sh` currently creates `testbed` with `python=3.10`. That is fine for many repos but will break those needing newer Python. We should allow profile- or repo-specific Python versions (or pass a version flag) instead of a single hard pin.
- `try_install_py` behavior: today it succeeds even if tests would fail due to missing deps. It only checks that the install script completes. A more robust behavior is to run a smoke test (or selected tests) and fail fast if imports/deps are missing.

### Fix forward
Long-term robust path (preferred):
1) Install test/dev deps during env export
   - Add a test-aware install step in `configs/install_repo.sh`: prefer `pip install -e .[test]` when extras exist, else fall back to `pip install -r requirements-test.txt` if present, else a repo-specific hook in the profile (`install_cmds`).
   - Allow a profile-level override for Python version (e.g., profile fields or a flag) so repos needing >3.10 can export with the correct interpreter.
2) Add a smoke-test gate to `try_install_py`
   - After install, run a quick pytest smoke (e.g., `pytest -q --maxfail=1`) or a repo-provided smoke command. Fail `try_install_py` if imports/deps are missing. This prevents exporting envs that can’t even collect tests. Running the full suite per repo may be slow; a short smoke test (single test or `pytest -q --maxfail=1`) strikes a balance. The key is to fail fast on missing imports so broken envs aren’t baked into images.
3) Re-export envs on linux/x86_64
   - Keep exporting on linux/x86_64 so build-time packages match the runtime platform.
4) Rebuild and push images from the validated envs
   - Once the smoke test passes, rebuild/push so evals won’t hit missing deps.

### Test Plan
- Update install logic to include test deps, re-run `try_install_py` on linux/x86_64, then rebuild/push the image. If needed, adjust the Python version per profile before export.
