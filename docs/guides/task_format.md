# Task Format

## Task Schema

```json
{
  "instance_id": "pylint-dev__astroid.b114f6b5.2496",
  "repo": "pylint-dev__astroid.b114f6b5",
  "patch": "diff --git a/astroid/nodes/node_classes.py ...",
  "FAIL_TO_PASS": [
    "tests/test_inference.py::test_formatted_fstring_inference"
  ],
  "PASS_TO_PASS": [
    "tests/test_inference.py::test_fstring_inference"
  ]
}
```

*   **instance_id**: Unique identifier.
*   **repo**: Matches a registered `RepoProfile` class name/key.
*   **patch**: The **bug-introducing** patch (i.e., the diff that creates the failing behavior). This corresponds to the **“Bug Patch”** commit created during dataset construction (see below) and is the code state the evaluator uses as `HEAD~1` when running tests.
    *   When you run evaluation with `--predictions_path gold`, the harness treats this as the “gold” reference by **reverse-applying** it in the container (so “gold fix” = revert of this patch).
*   **FAIL_TO_PASS**: Tests that fail without the fix and pass with it.
*   **PASS_TO_PASS**: Tests that must continue to pass to ensure no regressions.

## Comparison to SWE-bench

> [!IMPORTANT]
> **Patch meaning differs:** In SWE-bench, `patch` is the **oracle fix**; in SWE-smith, `patch` is the **bug-introducing** diff (and “gold” eval reverse-applies it).
> **Where is the test patch?**
>
> Unlike SWE-bench, the test patch is not a top-level field in the final dataset. Instead, it is baked into the git history of the repository mirror.
>
> *   For each task `instance_id`, a git branch named `instance_id` is created on the mirror repository.
> *   The dataset `patch` is applied and committed as **“Bug Patch”** (bug active + F2P test file(s) present).
> *   **HEAD**: The bug is active, and the F2P test file(s) are *removed* (a deterministic “Remove F2P Tests” commit; this "Remove F2P Tests" diff is **not** stored in the dataset).
> *   **HEAD~1**: The bug is active, and the F2P test file(s) are *present* (the “Bug Patch” commit).
>
> During evaluation, the harness checks out `HEAD~1` to run the tests. These mirror repositories are hosted on GitHub under the `swesmith` organization (e.g., `https://github.com/swesmith/pylint-dev__astroid.b114f6b5`).

| Feature | SWE-bench | SWE-smith |
| :--- | :--- | :--- |
| **Source** | Real GitHub Issues & PRs | Synthesized Tasks (and Real PRs) |
| **Quantity** | Fixed set (2,294 tasks) | Unlimited (can generate millions) |
| **Test Definition** | Existing tests in repo history | New tests injected via git history (`HEAD~1`) |
| **Repo Handling** | `constants.py` maps versions | `RepoProfile` classes per commit |

In SWE-smith, because we turn repositories into "gyms," we often generate thousands of tasks for a single repository state (commit). The git branch mechanism allows us to inject new failing tests (representing new requirements or bugs) into that static environment while keeping the task definition lightweight.
