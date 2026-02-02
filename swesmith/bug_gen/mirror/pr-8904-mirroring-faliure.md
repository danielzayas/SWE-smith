# PR-8904 Mirroring Failure (OkHttp)

## Problem Statement

TLDR: compilation failed due to a bad patch from the LLM response.

While attempting to mirror OkHttp PR-8904 using:

```bash
python -m swesmith.bug_gen.mirror.generate <task_instances.jsonl> --model <...>
```

the generated `bug__pr_8904.diff` (written under `logs/bug_gen/.../pr_mirror/.../bug__pr_8904.diff`) **applied** but **did not compile** on the target SWE-smith OkHttp profile commit (`danielzayas__okhttp.8e0cc1b3`). This caused the validation harness to fail early during Kotlin compilation:

- Validation log: `/Users/danielzayas/Development/SWE-bench/SWE-smith/logs/run_validation/square__okhttp.8e0cc1b3/square__okhttp.8e0cc1b3.pr_8904/test_output.txt`
- Failing Gradle task: `:okhttp:compileTestKotlinJvm FAILED`

```shell
> Task :okhttp:compileTestKotlinJvm FAILED
Build 60992c24-08a5-4590-b780-2eef71dbeaf4 is closed
Build 467a5257-568f-4c6c-be1c-77f9cef12f9a is closed

[Incubating] Problems report is available at: file:///testbed/build/reports/problems/problems-report.html

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':okhttp:compileTestKotlinJvm'.
> A failure occurred while executing org.jetbrains.kotlin.compilerRunner.GradleCompilerRunnerWithWorkers$GradleKotlinCompilerWorkAction
   > Compilation error. See log for more details
```

Because compilation failed, **no tests were executed**, so the validation report ended up with empty sets and the instance could not satisfy the “1+ FAIL_TO_PASS” requirement.

### Root cause: `bug__pr_8904.diff` introduces an invalid `exchange.trailers()` call in `Response.kt`

The Kotlin compiler error is in `Response.kt` and specifically reports `Unresolved reference 'trailers'` at the failing line. The generated patch adds a new `exchange.trailers()` call in `Response.Builder.initExchange()`, which introduces this unresolved symbol in the profile’s code state.

#### Evidence 1: Kotlin compiler errors (from validation output)

From:
`logs/run_validation/danielzayas__okhttp.8e0cc1b3/danielzayas__okhttp.8e0cc1b3.pr_8904/test_output.txt`

```text
e: file:///testbed/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Response.kt:513:29 Cannot infer type for type parameter 'T'. Specify it explicitly.
e: file:///testbed/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Response.kt:513:29 Cannot infer type for type parameter 'R'. Specify it explicitly.
e: file:///testbed/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Response.kt:513:29 Unresolved reference. None of the following candidates is applicable because of a receiver type mismatch:
fun <T, R> DeepRecursiveFunction<T, R>.invoke(value: T): R
e: file:///testbed/okhttp/src/commonJvmAndroid/kotlin/okhttp3/Response.kt:513:55 Unresolved reference 'trailers'.

> Task :okhttp:compileKotlinJvm FAILED
...
Execution failed for task ':okhttp:compileKotlinJvm'.
> ... Compilation error. See log for more details
```

This directly matches the patch hunk that adds `exchange.trailers()` in `Response.kt` (shown below).

#### Evidence 2: patch hunks that introduce the incompatible behavior

From:
`logs/bug_gen/danielzayas__okhttp.8e0cc1b3/pr_mirror/danielzayas__okhttp-8904/bug__pr_8904.diff`

```diff
@@
     internal fun initExchange(exchange: Exchange) {
       this.exchange = exchange
+      this.trailersSource = TrailersSource { exchange.trailers() }
     }
```

Problem (confirmed by compiler output):
- This adds `exchange.trailers()` to `Response.kt`. The validation compile log then reports `Unresolved reference 'trailers'` in `Response.kt`, and the build fails at `:okhttp:compileKotlinJvm FAILED`.

### Summary

The mirroring output `bug__pr_8904.diff` produced a patch that **applies** but **does not compile** against the OkHttp profile commit. The validation harness therefore cannot compute any FAIL_TO_PASS regressions, producing an invalid candidate instance.

## Proposed Fix

We should fix the mirroring pipeline so it **never emits** a “successful” mirrored bug patch that fails to compile.

### 1) Add a compilation gate after applying the candidate patch

In `SWE-smith/swesmith/bug_gen/mirror/generate.py`:

- After `apply_patches(...)` succeeds (both direct-apply and recovered/merged patch paths), run a **compile / test preflight** inside the profile environment.
  - Best option: run the profile’s test command (or a compile-only equivalent) in the same containerized environment used by validation.
  - For Kotlin/Gradle projects, a fast compile gate is often:
    - `./gradlew :okhttp:compileKotlinJvm --no-daemon` (or profile-specific)
  - If the gate fails (non-zero exit or “Compilation error”), treat the attempt as `recover_fail` and either:
    - retry recovery (if possible), or
    - mark the instance as failed and skip.

### 2) Add a post-check that rejects “unknown import / unknown symbol” patches

Before accepting the final merged patch:

- Parse the generated patch and extract any newly-added import lines (e.g. `+import ...`).
- For each new import:
  - Verify the imported package/class/function exists in the target repo checkout **at the profile commit**.
  - If not resolvable, reject and retry recovery.

This prevents “invented imports” that don’t exist in the target repo at the profile commit, which is a common way for mirroring patches to become non-compilable.

### 3) Make “success” require at least: applies + compiles

Change the definition of “Recovery Success” from:

- “Patch applied cleanly”

to:

- “Patch applied cleanly **and** compile gate passes”

This avoids producing mirrored bug patches that are unusable for validation.

### 4) (Optional) Improve recovery prompt constraints

Update mirroring prompts (or add a validation step) so the LLM is discouraged from:

- Introducing new imports or new APIs not already referenced in the file.
- Refactoring across files unless necessary.

## Notes / Follow-ups

- Once compilation passes consistently, validation should start producing non-empty `FAIL_TO_PASS` for this instance (assuming the mirrored bug actually breaks tests that pass on the baseline).
- If compilation succeeds but `FAIL_TO_PASS` is still empty, the next debugging step is behavioral (the bug isn’t causing regressions under the profile’s test cmd), not structural.


