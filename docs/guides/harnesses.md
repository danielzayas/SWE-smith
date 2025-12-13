# Validation & Evaluation

Great! You now have an execution environment + a bunch of candidate task instances. How do we determine which ones can be used for training?

We provide two harnesses for the purposes of:

* Validation: To check if a candidate task instance is usable (breaks 1+ existing tests).
* Evaluation: To check if the proposed solution for a task instance is correct.

The purposes of these harnesses are identical to their motivations in [SWE-bench](https://swe-bench.github.io).

## Validation

The validation harness is used to check if a candidate task instance is usable (breaks 1+ existing tests). For example:
```
python -m swesmith.harness.valid logs/bug_gen/<repo>_all_patches.json
```

### Validation Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SWE-smith Validation System                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Candidate Patches (JSON)                                                   │
│  ├─ instance_id                                                             │
│  ├─ repo (RepoProfile key)                                                  │
│  └─ patch (Bug-inducing patch)                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  harness/valid.py (Main Entry Point)                                        │
│  ├─ Loads candidate patches                                                 │
│  ├─ Resolves RepoProfile for each instance                                  │
│  ├─ Manages parallel execution (ThreadPool)                                 │
│  └─ Coordinates Pre-Gold vs Post-Gold runs                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXECUTION LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Docker Environment (RepoProfile.image_name)                                │
│                                                                             │
│  Run 1: Pre-Gold (Baseline)                                                 │
│  ├─ Start Container (Clean state)                                           │
│  ├─ Run Tests (RepoProfile.get_test_cmd)                                    │
│  └─ Capture Output (Pre-Gold Logs)                                          │
│                                                                             │
│  Run 2: Post-Gold (Buggy)                                                   │
│  ├─ Start Container                                                         │
│  ├─ Apply Bug Patch (Candidate)                                             │
│  ├─ Run Tests (RepoProfile.get_test_cmd)                                    │
│  └─ Capture Output (Post-Gold Logs)                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GRADING LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  harness/grading.py -> get_valid_report                                     │
│  1. Parse Pre-Gold Logs (TestStatus.PASSED?)                                │
│  2. Parse Post-Gold Logs (TestStatus.FAILED?)                               │
│  3. Identify Regressions (FAIL_TO_PASS)                                     │
│     └─ Tests that passed in Run 1 but failed in Run 2                       │
│  4. Filter: If len(FAIL_TO_PASS) > 0 -> VALID INSTANCE                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Repository Architecture for Orchestrating Validations

The validation logic in `swesmith.harness.valid` follows this pipeline:

1.  **Entry**: `valid.py` reads a list of candidate patches (potential bugs).
2.  **Profile Resolution**: It identifies the `RepoProfile` for the repository.
3.  **Baseline Establishment (Pre-Gold)**:
    *   It runs the test suite on the clean repository state (no patch).
    *   This establishes which tests *should* pass in a healthy state.
4.  **Bug Verification (Post-Gold)**:
    *   It applies the candidate "bug" patch to the repository.
    *   It runs the test suite again.
5.  **Comparison**:
    *   It compares the two runs.
    *   A valid task must cause at least one test to flip from PASS (pre-gold) to FAIL (post-gold). These become the `FAIL_TO_PASS` tests for the task.
    *   Tests that remain passing are recorded as `PASS_TO_PASS`.
6.  **Output**: Valid instances are saved with their `FAIL_TO_PASS` and `PASS_TO_PASS` lists.

### Usage

Once you've generated task instance candidates, follow these steps to validate them:

1. Collect the candidates

```bash
python -m swesmith.bug_gen.collect_patches logs/bug_gen/<repo>
```

This produces a `logs/bug_gen/<repo>_all_patches.json` file with all the candidate task instances.

2. Run validation

```bash
python -m swesmith.harness.valid logs/bug_gen/<repo>_all_patches.json
```

The validation harness works in two steps.
First, it runs the original repository's test suite to get the passing statuses of the existing tests.
Then, it applies each candidate task instance to the repository and runs the test suite again.
If the candidate task instance breaks 1+ existing tests, it is considered a usable task instance.

For each task instance, the validation harness produces a `logs/run_validation/<run_id>/<instance_id>` folder containing the following information:

* `eval.sh`: The sequence of test command(s) run
* `patch.diff`: The candidate task instance
* `report.json`: `FAIL_TO_PASS` and `PASS_TO_PASS` test cases
* `run_instance.log`: The full trace of running validation
* `test_output.txt`: The standard output of the test command(s)

3. Collect validated task instances

```bash
python -m swesmith.harness.gather logs/run_validation/<run_id>
```

Task instances with 1+ `FAIL_TO_PASS` test cases and 1+ `PASS_TO_PASS` test cases are considered valid.

This script performs two actions:

* It collects all valid task instances into a `logs/task_insts/<run_id>.json`. Each instance contains the following information:
```json
{
    "instance_id": <instance_id>,
    "repo": <repo>,
    "patch": <The diff that, when applied, creates the bug>,
    "FAIL_TO_PASS": <List of broken test cases>,
    "PASS_TO_PASS": <List of passing test cases>,
    "image_name": <docker image name>,
}
```
* For each valid task instance, a branch called `<instance_id>` is created in the repository. The branch corresponds to the repository with the task instance's bug patch applied.

---

## Evaluation

The evaluation harness is used to check if the proposed solution for a task instance is correct.

### Evaluation Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SWE-smith Evaluation System                        │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              INPUT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Dataset (HuggingFace/Local)              Predictions (JSON/JSONL)          │
│  (Unlimited Synthesized Tasks)            ├─ instance_id                    │
│  ├─ instance_id                           ├─ model_name_or_path             │
│  ├─ repo (RepoProfile key)                └─ model_patch                    │
│  ├─ patch (Gold - optional)                                                 │
│  ├─ instance_ref (Internal)                                                 │
│  │  └─ test_patch (Baked into git history)                                  │
│  ├─ FAIL_TO_PASS (tests)                                                    │
│  └─ PASS_TO_PASS (tests)                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  harness/eval.py (Main Entry Point)                                         │
│  ├─ Loads dataset & predictions                                             │
│  ├─ Resolves RepoProfile for each instance                                  │
│  ├─ Manages parallel execution                                              │
│  └─ Generates reports                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PROFILE LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  RepoProfile (Object-Oriented Config)                                       │
│  (One Singleton per Repo/Commit)                                            │
│  ├─ Defines Environment (Dockerfile)                                        │
│  ├─ Defines Installation (install_cmds)                                     │
│  ├─ Defines Test Command (get_test_cmd)                                     │
│  └─ Manages Docker Images (Build/Pull)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXECUTION LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Docker Environment                                                         │
│  1. Start Container (from RepoProfile image)                                │
│  2. Checkout the task instance branch (instance_id)                         │
│  3. Checkout HEAD~1 to restore hidden F2P test files (tests removed at HEAD)│
│  4. Apply model patch (and revert any changes the patch makes to test files)│
│  5. Run Tests (RepoProfile.get_test_cmd)                                    │
│  6. Capture Output                                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           GRADING LAYER                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  harness/grading.py                                                         │
│  1. Parse Logs (RepoProfile.log_parser)                                     │
│  2. Compare Results (FAIL_TO_PASS / PASS_TO_PASS)                           │
│  3. Determine Resolution Status                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Repository Architecture for Orchestrating Evaluations

The orchestration logic in SWE-smith differs from SWE-bench to support its scale and dynamic nature.

#### The `swesmith.harness.eval` Pipeline

1.  **Entry**: `eval.py` reads the dataset and predictions.
2.  **Profile Resolution**: For each instance, it looks up the corresponding `RepoProfile` using the `repo` field.
3.  **Execution**:
    *   It does *not* build images on the fly for every task. Instead, it assumes the `RepoProfile`'s base environment image is pre-built.
    *   It starts a container from that profile's image.
    *   It checks out the task instance branch (`instance_id`) inside the container.
        *   **Branch-per-task requirement**: SWE-smith evaluation assumes **one git branch per task instance** whose name is exactly the task’s `instance_id`. This branch is created and pushed during dataset construction (see `swesmith/harness/gather.py`, which runs `git checkout -b <instance_id>` and `git push origin <instance_id>`).
    *   **Test-hiding / reveal mechanic**: SWE-smith task branches are expected to have **two commits**:
        *   Commit A: the **buggy** state *with* the relevant F2P tests present.
        *   Commit B (branch `HEAD`): a follow-up commit that **removes the F2P test file(s)** so the agent can generate a fix without reading them.
        During evaluation, the harness checks out the branch tip and then runs `git checkout HEAD~1` to return to Commit A, which **restores the hidden F2P tests** before executing the test command.
    *   It applies the model patch on top of that “bug + tests restored” working tree (`swesmith/harness/utils.py`).
    *   It explicitly reverts any changes the model patch made to test files (both F2P and P2P) to prevent solutions that “fix” the task by editing tests (`swesmith/harness/utils.py`).
    *   It runs the test command returned by `RepoProfile.get_test_cmd(...)` and captures the raw output.
        *   Depending on the profile, this may run the full suite, or a minimized subset (see `RepoProfile.min_testing`), and `--f2p_only` can further restrict the command to just the F2P test files.
4.  **Grading**: The harness parses the test output with `RepoProfile.log_parser(...)` and computes resolution/maintenance against the instance’s `FAIL_TO_PASS` and `PASS_TO_PASS` lists (optionally filtered when `--f2p_only` is enabled).

**Key source code references (SWE-smith)**:
- **Orchestration / entrypoint**: `swesmith/harness/eval.py`
- **Container execution + git checkouts + apply-patch + “don’t edit tests” enforcement**: `swesmith/harness/utils.py` (`run_patch_in_container`, `_apply_patch`)
- **Test command selection / minimization**: `swesmith/profiles/base.py` (`RepoProfile.get_test_cmd`, `RepoProfile.min_testing`)
- **Mapping tests → files (used for `--f2p_only` and for reverting test-file edits)**: `swesmith/profiles/python.py` (`PythonProfile.get_test_files`) and analogous language profiles
- **Evaluation grading logic**: `swesmith/harness/grading.py` (`get_eval_report`, `get_eval_tests_report`). SWE-smith re-uses `SWE-bench/swebench/harness/grading.py` (`get_resolution_status`) during grading.

#### The `RepoProfile` Abstraction

Unlike SWE-bench, which uses large dictionaries in `constants.py` to define environments, SWE-smith uses an object-oriented approach.

**File**: `swesmith/profiles/base.py` & `swesmith/profiles/python.py`

Each supported repository-commit pair is a class:

```python
@dataclass
class AstroidB114f6b5(PythonProfile):
    owner: str = "pylint-dev"
    repo: str = "astroid"
    commit: str = "b114f6b58e749b8ab47f80490dce73ea80d8015f"
    
    # Inherits build logic, test commands, and log parsers from PythonProfile
```

This class defines:
*   **Environment**: How to build the Docker image for this specific commit.
*   **Installation**: How to install the package (e.g., `pip install -e .`).
*   **Testing**: How to run tests (e.g., `pytest`).
*   **Parsing**: How to read test results.

### Usage

You can run this script to sanity check that testing for validated task instances works as expected:

```bash
python -m swesmith.harness.eval \
    --dataset_path bugs/task_insts/{repo}.json \
    --predictions_path gold \
    --run_id sanity
```

If you want to run on real predictions, simply replace `gold` with the path to your predictions, which should look like:

```json
{
    "instance_id": <instance_id>,
    "patch": <The diff that, when applied, fixes the bug>,
    "model_name_or_path": <The model used to generate the patch>,
}
```
