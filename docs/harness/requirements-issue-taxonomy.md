# Requirements Issue Taxonomy

This document defines the GitHub issue taxonomy that the requirements assistant must use when it turns an approved requirements draft into generated planning issues.

The policy is product-local for Orcha until it is deliberately promoted into the shared `agent-core` baseline.

## Scope

The taxonomy applies to issues generated from a requirements assistant draft, including:

- parent epics
- feature work
- API work
- spikes
- bugs
- chores

It does not rewrite historical issues, replace GitHub Project status mappings, or define the publication API. Publication code must treat this document as the validation contract.

## Issue Types

Every generated issue must have exactly one `type:*` label. More than one type label is invalid. Zero type labels is invalid.

Allowed type labels:

| Issue kind | Required type label | Title prefix | Template baseline |
| --- | --- | --- | --- |
| Epic | `type:epic` | `[Epic]` | Feature-style body sections plus `Child issues` when known. |
| Feature | `type:feature` | `[Feature]` | `.github/ISSUE_TEMPLATE/feature.yml` |
| API | `type:feature` | `[API]` | `.github/ISSUE_TEMPLATE/api.yml` |
| Spike | `type:spike` | `[Spike]` | `.github/ISSUE_TEMPLATE/spike.yml` |
| Bug | `type:bug` | `[Bug]` | Feature-style body sections with reproduction and expected behavior in Requirements or Acceptance criteria. |
| Chore | `type:chore` | `[Chore]` | Feature-style body sections focused on operational or maintenance outcome. |

API issues intentionally use `type:feature` in the current Orcha baseline because `.github/ISSUE_TEMPLATE/api.yml` seeds that label. Do not introduce `type:api` unless the target product repository explicitly adopts that label in a later taxonomy revision.

`type:bug` and `type:chore` are allowed generated issue types, but a product repository may not have those labels yet. Missing label behavior is defined below.

## Required Body Sections

Generated issue bodies must use Markdown headings that match the repo issue templates. Required sections are case-sensitive for validation.

### Epic

Required sections:

- `Outcome`
- `Requirements (testable)`
- `Child issues`
- `Non-goals (explicitly out of scope)`
- `Impacted areas`
- `Acceptance criteria`
- `Demo / test plan`
- `Dependencies / open questions`
- `Agent brief (optional)`

`Child issues` may list generated client ids before GitHub issue numbers exist. After publication, mirror or audit code may rewrite those references with issue numbers.

### Feature, Bug, And Chore

Required sections:

- `Outcome`
- `Requirements (testable)`
- `Non-goals (explicitly out of scope)`
- `Impacted areas`
- `Acceptance criteria`
- `Demo / test plan`
- `Dependencies / open questions`
- `Agent brief (optional)`

Feature-style work is not ready to publish when any required section is missing, empty, or only restates the title.

### API

Required sections:

- `Outcome`
- `Endpoints (method + path)`
- `Request / response contract`
- `Errors and status codes`
- `Compatibility / rollout notes`
- `Acceptance criteria`
- `Demo / test plan`
- `Dependencies / open questions`
- `Agent brief (optional)`

API issues must state authentication and authorization expectations with each endpoint, even when the answer is "same product workspace permissions as existing agent chat routes."

### Spike

Required sections:

- `Question to answer`
- `Timebox`
- `Required output artifact`
- `Decision needed at the end`
- `Notes / constraints (optional)`

Use a spike when the assistant cannot produce executable requirements without first choosing an implementation path, validating an external constraint, or confirming a design decision.

## Label Classes

Generated issues use labels from these classes:

| Class | Required | Examples | Rule |
| --- | --- | --- | --- |
| Type | Yes, exactly one | `type:epic`, `type:feature`, `type:spike` | Blocks publication when missing, duplicated, or unsupported. |
| Feature | Recommended | `feature:requirements-assistant` | Required when the draft belongs to a known product feature area. |
| Area | Recommended | `area:api`, `area:web`, `area:github`, `area:docs` | Include every directly impacted implementation area. |
| Source | Optional | `source:requirements-assistant` | Use when the target repository has adopted source labels. Do not invent unsupported source labels silently. |
| State | No | `blocked`, `needs-decision` | Avoid initial state labels unless the generated issue is intentionally blocked. Prefer Project status. |

The requirements assistant must preserve labels already listed in an approved draft only if they match the target repository policy. Unknown labels are publication warnings until the publisher can either create them safely or block on missing permission.

## Standard Labels

The current Orcha requirements assistant backlog uses these labels:

| Label | Purpose |
| --- | --- |
| `feature:requirements-assistant` | Groups requirements assistant work. |
| `area:agent-chat` | Chat workspace, files, runs, outputs, and assistant conversation state. |
| `area:api` | Platform API contract, persistence, and service behavior. |
| `area:web` | Operator web UI and UX. |
| `area:worker` | Background worker or asynchronous processing. |
| `area:github` | GitHub issue, PR, project, repository, and mirror integration. |
| `area:mcp` | MCP tools and internal agent tool contracts. |
| `area:docs` | Durable docs, planning artifacts, and taxonomy changes. |
| `area:standards` | Standards packs, harness context, and baseline governance. |

Publication code may create missing labels only when all of these are true:

- the label name matches an allowed prefix and pattern
- the label color and description are known from the assistant plan or repo policy
- the product repository binding has label write permission
- the create-label result is recorded in publication audit evidence

When label creation is not permitted, the publisher must not publish unlabeled type work silently. Required missing type labels block publication. Missing recommended feature or area labels create warnings unless the issue would become untriageable without them.

## Titles

Generated titles must be short and actionable.

Title rules:

- start with the standard prefix for the issue kind
- use sentence case after the prefix
- name the outcome, not the implementation branch
- avoid "Phase 1", "misc", "follow-up", and other labels that only make sense inside a private plan
- avoid closing keywords

Examples:

- `[Epic] Publish standardized requirements plans to GitHub`
- `[Feature] Validate generated issue labels before publication`
- `[API] Add requirements issue dry-run endpoint`
- `[Spike] Choose GitHub project placement failure policy`

## Relationships

Generated issue relationships must never use accidental closing keywords.

Allowed relationship text:

- `Part of #123`
- `Part of <client-issue-id>` before publication
- `Depends on #123`
- `Depends on <client-issue-id>` before publication
- `Blocked by #123`

Disallowed relationship text in generated issue bodies:

- `Closes #123`
- `Fixes #123`
- `Resolves #123`

Closing keywords belong in pull request bodies, not generated planning issues, unless a human explicitly asks the assistant to close an existing issue.

When a generated child belongs to a generated epic, put the relationship in `Dependencies / open questions` as `Part of <epic-client-id>` during dry-run. After publication, replace the client id with the created GitHub issue number.

When dependency order matters, publish parents before children and dependencies before dependent work. If a dependency target is ambiguous, block `ready_to_publish`.

## Project Status

Generated issues start in the product repository intake state:

- use the product-configured raw Project status when available, commonly `Todo`
- normalize that state to Orcha `Triage` in mirror/work-item read models
- do not promote generated issues directly to `Ready` unless a human-approved publication flow explicitly requests it

Generated issues must be reviewable as backlog intake after publication. They should not imply that an implementation lane is already running.

## Validation Rules

A generated requirements draft is not `ready_to_publish` unless all checks pass.

Blocking validation errors:

- no proposed issues
- any proposed issue has zero or multiple `type:*` labels
- a proposed issue has a type label outside the allowed set
- required body sections are missing or empty for the issue kind
- a feature-style issue lacks `Outcome`, `Requirements (testable)`, `Acceptance criteria`, or `Demo / test plan`
- an API issue lacks endpoint, contract, error, compatibility, acceptance, or test-plan detail
- a spike lacks question, timebox, output artifact, or decision detail
- parent or dependency references point to unknown client ids or missing GitHub issue numbers
- required labels are missing and cannot be created with current repository permissions
- the draft uses closing keywords in generated issue bodies
- any blocking clarification question remains open

Warnings that do not always block publication:

- missing recommended feature label
- missing recommended area label
- project placement unavailable after issue creation
- source label unsupported by the target repository
- generated issue body has optional `Agent brief` omitted

Warnings become blockers when they would prevent a contributor or agent lane from executing the issue without guessing.

## Dry-Run Output Expectations

Dry-run publication must show:

- generated issue order
- title
- type label
- full label set
- parent references
- dependency references
- body section completeness
- missing labels and whether they will be created
- project placement target or warning
- publication blockers

The dry-run result is the human review artifact that should be approved before live GitHub publication.

## Examples

Feature issue skeleton:

```markdown
## Outcome
Operators can validate generated requirement issues before publication.

## Requirements (testable)
- Validate exactly one type label per generated issue.
- Report missing area labels as warnings unless repository policy requires them.

## Non-goals (explicitly out of scope)
- Publishing implementation pull requests.

## Impacted areas
- [x] API changes
- [ ] Background worker or service changes
- [ ] Web or UX changes
- [ ] Infra or deploy changes
- [x] Docs updates
- [ ] Telemetry or observability updates

## Acceptance criteria
- Given a generated feature issue with two type labels, when validation runs, then publication is blocked.

## Demo / test plan
1. Run the taxonomy validator fixture for duplicate type labels.

## Dependencies / open questions
- Part of #344.
- Depends on #352.

## Agent brief (optional)
- Target areas: packages/platform-api.
- Constraints: do not emit closing keywords in generated issue bodies.
```

Spike issue skeleton:

```markdown
## Question to answer
Which GitHub project placement failure modes should block requirements publication?

## Timebox
4 hours

## Required output artifact
- Decision note in docs/planning or docs/harness.
- Follow-up issue updates if the publication API contract changes.

## Decision needed at the end
- Treat project placement failure as blocking, warning-only, or configurable.

## Notes / constraints (optional)
- GitHub issue creation success must not be rolled back if project placement fails after issue creation.
```
