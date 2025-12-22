# PR Mirroring

This document details the architecture and process of **PR Mirroring**, a technique used in SWE-smith to create bug reproduction instances from existing Pull Requests (PRs).

## How does it work?
<div style="text-align:center">
  <img src="../../assets/pr_mirror.png" alt="SWE-smith" style="width:100%"/>
</div>

The goal of PR Mirroring is to transform a Pull Request—specifically one that fixes a bug or implements a feature—into a standalone task instance for SWE-agent evaluation. This allows us to "mine" thousands of realistic tasks from open source repositories history.

The core challenge is that simply checking out the parent commit of a PR often isn't enough to create a stable environment or a compatible testbed, especially for older PRs. Instead, PR Mirroring attempts to "port" the bug to the *current* (or a more recent) version of the repository. It does this by using a Large Language Model (LLM) to **reverse** the changes introduced by the PR, effectively re-introducing the bug into the modern codebase.

This method leverages SWE-bench's [task collection script](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/collect/run_get_tasks_pipeline.sh).

Run the script for a repository, and it will create a `<repo>-task-instances.jsonl.all`.
This file contains candidate task instances based on real pull requests (PRs) from the repository.
A pull request is considered a candidate if

* It has at least 1+ issue associated with it. TODO @danielzayas: consider relaxing this requirement in the future.
* It edits at least 1+ code file.
* It must edit at least 1+ test file(s) to provide `FAIL_TO_PASS` tests.

We provide this file to SWE-smith.
Per PR, we ask an LM to revert the PR's changes file by file.
If this process succeeds, we create a candidate task instance that effectively undoes the PR.

## How do I run it?
```bash
python -m swesmith.bug_gen.mirror.generate $file \
    --model openai/o3-mini
```

## Architecture Diagram

The following diagram illustrates the control flow for processing a single PR candidate.

```mermaid
graph TD
    A[Start: PR Candidate] --> B{Validation / Heuristics}
    B -->|Failed| C[Skip Instance]
    B -->|Passed| D{Attempt Direct Apply?}
    
    D -->|Success| E[Path 1: Direct Apply]
    E --> F[Save Original Patch]
    D -->|Fail| G[Path 2: Recovery / Mirror]
    
    G --> H[Loop through Changed Files]
    H --> I[LLM Reverses Changes<br/>(RECOVERY_PROMPT)]
    I --> J[Generate Reversal Patch per File]
    J --> K{All Files Processed?}
    K -->|No| H
    K -->|Yes| L[Merge Patches]
    
    L --> M{Verify Application}
    M -->|Success| N[Output Artifacts]
    M -->|Fail| O[Mark Recovery Failed]
    F --> N
```

### Path 1: Direct Apply
If the repository is currently in a state where the PR has *not* been applied (e.g., the PR is unmerged, or the repo head is an ancestor), we can sometimes apply the PR patch directly. In this case, the "bug" is the state before the patch, and the patch itself is the solution.

### Path 2: Recovery (The "Mirror")
If the repository already contains the changes (e.g., the PR was merged), we must **remove** them to reproduce the bug. This is the primary function of PR Mirroring. The LLM analyzes the diff and rewrites the code to its state *before* the PR, creating a "Reversal Patch".

## Key Components

### `process_single_instance`
The main orchestrator function located in `swesmith.bug_gen.mirror.generate`. It:
1.  Sets up a secluded temporary environment for the worker.
2.  Clones the target repository.
3.  Runs validation checks (e.g., ensuring the PR doesn't touch too many files or binary files).
4.  Decides whether to use the **Direct Apply** path or the **Recovery** path.

### `recover_sweb_inst`
This function handles the logic for the Recovery path. It iterates through every file modified in the PR:
-   **Added Files**: It removes them.
-   **Removed Files**: It restores them (using content from the diff).
-   **Modified Files**: It invokes the LLM to rewrite the file content.

### `RECOVERY_PROMPT`
The prompt used to instruct the LLM to reverse changes. It provides:
-   The current source code of the file (Post-PR).
-   The diff patch showing what changed.
-   Strict instructions to "undo" the specific changes (remove added lines, add back removed lines) while leaving the rest of the code untouched.

### `get_patch`
A utility function that captures the difference between the current working directory and the HEAD commit. In the Recovery path, this captures the "Reversal Patch" (HEAD -> Buggy State).

## Output Artifacts

For each processed instance, the following artifacts are generated in the log directory (`logs/bug_gen/<repo>/pr_mirror/<instance_id>/`):

1.  **`bug__pr_<PR_NUM>.diff`**
    -   In **Recovery Path**: This is the "Reversal Patch". Applying it to the current codebase *introduces* the bug.
    -   In **Direct Path**: This is the original PR patch. Applying it *fixes* the bug.
2.  **`metadata__pr_<PR_NUM>.json`**
    -   Contains execution details such as `recover_status` ("success", "failed", "skipped"), LLM usage costs, and the raw rewrites generated by the model.
3.  **`ref__pr_<PR_NUM>.diff`**
    -   The original PR patch, saved for reference and potentially used as the "Golden Patch" (solution) for the final task instance.

## FAIL_TO_PASS (F2P) test requirements

`SWE-smith/swesmith/harness/valid.py` considers a a candidate task instance is usable if breaks 1+ existing tests, which implies that tasks created from the PR mirroring technique must have at least one fail-to-pass test. 

The subset of PR Mirroring tasks in the hugging face "[SWE-bench/SWE-smith](https://huggingface.co/datasets/SWE-bench/SWE-smith/viewer/default/train?views%5B%5D=train&sql=--+The+SQL+console+is+powered+by+DuckDB+WASM+and+runs+entirely+in+the+browser.%0A--+Get+started+by+typing+a+query+or+selecting+a+view+from+the+options+below.%0A--+SELECT+*%0A--+FROM+train+%0A--+where+instance_id+like+%27%25.pr_%25%27%0A--+limit+30%0A--+%3B%0A%0ASELECT+*%0AFROM+train+%0Awhere+instance_id+like+%27%25.pr_%25%27%0Aorder+by+len%28FAIL_TO_PASS%29%0Alimit+30%0A%3B%0A)" dataset have 1+ FAIL_TO_PASS tests:
```sql
SELECT *
FROM train 
where instance_id like '%.pr_%'
order by len(FAIL_TO_PASS)
limit 30
;
```
