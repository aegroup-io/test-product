# Architecture Docs

`docs/architecture/` is the canonical home for durable technical context inside a product repo that adopts the `agent-core` baseline.

Put docs here when they answer questions like:

- What technical boundaries should this product preserve?
- What implementation constraints are durable rather than issue-local?
- Which local domain concepts are intentionally outside shared baseline?

Do not put contributor workflows or exploratory proposals here:

- Use `docs/harness/` for contributor workflows.
- Use `docs/planning/` for evolving proposals and backlog shaping.

Current canonical docs:

- [`platform-stack.md`](platform-stack.md) for the fixed Azure, Kubernetes, App Service, APIM, and Terraform baseline assumptions inherited from `agent-core`.
- [`orcha-control-plane-foundations.md`](orcha-control-plane-foundations.md) for the durable ownership boundary between retained `agent-core` platform primitives and Orcha-owned control-plane state.
- [`product-contract-and-activation.md`](product-contract-and-activation.md) for the repo-local product manifest, effective config precedence, and activation-preflight semantics.
- [`product-seeding.md`](product-seeding.md) for onboarding workflows that render the approved baseline, register products, and gate activation on seed-time preflight.
- [`github-app-and-delivery-ledger.md`](github-app-and-delivery-ledger.md) for GitHub webhook configuration, signed intake, and the replayable delivery ledger.
- [`github-mirror-and-repair.md`](github-mirror-and-repair.md) for local GitHub mirror tables, transactional webhook projection, and targeted repair semantics.
- [`standards-pack-upgrades.md`](standards-pack-upgrades.md) for versioned standards packs, per-product overrides, and reviewable upgrade or advisory run provenance.
- [`component-graph-and-topology-ingest.md`](component-graph-and-topology-ingest.md) for declared topology ingest, source precedence, and explicit graph freshness semantics.
- [`work-item-normalization.md`](work-item-normalization.md) for canonical scheduler-facing lifecycle mapping, dependency normalization, PR handoff, and repair semantics.
- [`durable-scheduling-and-lane-claiming.md`](durable-scheduling-and-lane-claiming.md) for eligibility evaluation, multi-scope quotas, fair ordering, claim ownership, and durable lane-transition evidence.
- [`remote-execution-environments.md`](remote-execution-environments.md) for claimed-lane provisioning, workspace hydration, continuation-safety, and cleanup semantics.
- [`runner-protocol-and-session-events.md`](runner-protocol-and-session-events.md) for the durable `agent-core` launch contract, handshake state, event persistence, pause semantics, and timeout/error mapping.
- [`graph-overlays-and-context-slices.md`](graph-overlays-and-context-slices.md) for operational overlays on the component graph, bounded slice read models, prompt-context shaping, and freshness semantics.
- [`governance-and-production-readiness.md`](governance-and-production-readiness.md) for durable approval posture, runner-side governance enforcement, secret redaction, runtime identity scope, and write-audit semantics.
- [`observability-and-operator-notifications.md`](observability-and-operator-notifications.md) for structured signal correlation, fleet and lane observability read models, and operator-visible notification semantics.
- [`retry-recovery-and-reconciliation.md`](retry-recovery-and-reconciliation.md) for transient retry policy, startup recovery, active-lane reconciliation, and orphan cleanup semantics.
- [`operator-api-v1.md`](operator-api-v1.md) for the versioned operator contract, read-model composition, intervention semantics, and current RBAC boundary.
- [`operator-web-ui.md`](operator-web-ui.md) for the Orcha-native web route topology, operator shell boundary, and `/v1` read-model binding.
