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
*   **patch**: The gold solution patch (optional for evaluation, used for validation).
*   **FAIL_TO_PASS**: Tests that fail without the fix and pass with it.
*   **PASS_TO_PASS**: Tests that must continue to pass to ensure no regressions.

## Comparison to SWE-bench

> [!IMPORTANT]
> **Where is the test patch?**
>
> Unlike SWE-bench, the test patch is not a top-level field in the final dataset. Instead, it is baked into the git history of the repository mirror.
>
> *   For each task `instance_id`, a git branch named `instance_id` is created on the mirror repository.
> *   **HEAD**: The bug is active, and the new test file reproducing the bug is *removed*.
> *   **HEAD~1**: The bug is active, and the new test file is *present*.
>
> During evaluation, the harness checks out `HEAD~1` to run the tests. These mirror repositories are hosted on GitHub under the `swesmith` organization (e.g., `https://github.com/swesmith/pylint-dev__astroid.b114f6b5`).

| Feature | SWE-bench | SWE-smith |
| :--- | :--- | :--- |
| **Source** | Real GitHub Issues & PRs | Synthesized Tasks (and Real PRs) |
| **Quantity** | Fixed set (2,294 tasks) | Unlimited (can generate millions) |
| **Test Definition** | Existing tests in repo history | New tests injected via git history (`HEAD~1`) |
| **Repo Handling** | `constants.py` maps versions | `RepoProfile` classes per commit |

In SWE-smith, because we turn repositories into "gyms," we often generate thousands of tasks for a single repository state (commit). The git branch mechanism allows us to inject new failing tests (representing new requirements or bugs) into that static environment while keeping the task definition lightweight.
