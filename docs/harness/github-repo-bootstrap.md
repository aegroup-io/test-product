# GitHub Repo Bootstrap

This document is the canonical per-repo setup checklist for the currently extracted `agent-core` harness baseline.

## Scope

The current baseline includes:

- `.github/workflows/repo-harness.yml`
- `.github/workflows/advisory-code-review.yml`
- `.github/workflows/merge-readiness.yml`

The repo-harness workflow does not require GitHub Actions secrets or variables.

## Rollout Checklist

1. Apply the managed baseline files into the target repo.
2. Confirm `.github/workflows/repo-harness.yml`, `.github/workflows/advisory-code-review.yml`, and `.github/workflows/merge-readiness.yml` exist in the target repo.
3. Set `OPENAI_API_KEY` if you want the advisory review workflow to run Codex review in CI.
4. Optionally set `CODEX_REVIEW_MODEL` if you want to override the default model.
5. For GitHub-hosted runners, set the advisory workflow job to export `CODEX_SANDBOX_MODE=danger-full-access` so Codex does not rely on `bwrap`.
6. Open a small test pull request.
7. Confirm the `Repo Harness` workflow runs successfully.
8. Confirm the `Advisory Code Review` workflow either:
   - runs a real review when `OPENAI_API_KEY` is configured, or
   - writes a `review-unavailable` artifact and summary when the secret is absent
9. Confirm the `Merge Readiness` workflow:
   - writes a `merge-readiness` artifact bundle
   - maintains a single merge-readiness pull request comment
   - reflects `Repo Harness` and `Advisory Code Review` state in its summary
10. If the repo later adds visual-regression workflows, document whether baseline acceptance is evidence capture only or whether it actually unblocks the same PR. Do not leave that policy implicit.

## Current Expectations

The repo-harness workflow should:

- check out the repo
- run `bash scripts/smoke_local.sh`
- validate managed assets, exercise the merge-readiness self-test, and compile the local `scripts/` directory

The advisory review workflow should:

- run on pull requests targeting `dev`
- use `OPENAI_API_KEY` when present
- use `CODEX_SANDBOX_MODE=danger-full-access` on GitHub-hosted runners
- upload the advisory artifact bundle
- write a single advisory summary comment
- degrade to `review-unavailable` instead of hard-failing when the secret is absent

The merge-readiness workflow should:

- run on pull request edits, review events, and workflow completions from `Repo Harness` and `Advisory Code Review`
- upload the readiness artifact bundle
- write a single merge-readiness summary comment
- degrade to `ready-with-risks` for fork pull requests instead of attempting repo-local readiness evaluation

If these workflows fail after baseline adoption, either:

- required managed files are missing
- managed docs drifted
- the repo-local harness validator was edited incompatibly
- advisory review prerequisites are missing or misconfigured
- merge-readiness prerequisites are missing or misconfigured

## Future Expansion

Later baseline extractions may add additional workflow setup requirements for:

- visual review
- baseline-acceptance workflows for visual diffs

When visual-review assets are later added, this checklist must explicitly call out whether accepted PR-branch baselines are used for comparison on the same PR or whether the base-branch baseline still controls the gate.
