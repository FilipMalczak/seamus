# 0058: Coverage Baseline, Test Tiers, and the Zero-Uncovered Floor

- **Status**: Accepted
- **Date**: 2026-11-14
- **Branch**: `0058-coverage-baseline`
- **Supersedes**: None

## Context

[0057-e2e-test-suite.md](./0057-e2e-test-suite.md) introduced a deterministic end-to-end suite and
produced the first feature/requirement/invariant to test traceability map
([test_coverage.md](../knowledge/test_coverage.md)). That map exposed a structural weakness in how
the suite was shaped: it was built around the behaviours that were easiest to reach, not around the
behaviours that exist.

The result was a lopsided distribution. A handful of subsystems — conversation streaming, plan
lifecycle, branching, Sync PRs — had several end-to-end tests each. Many others had exactly one
unit test, or none at all. Five requirements and six invariants had no test whatsoever. The
coverage was not merely uneven; it was *inconsistent*, which makes it impossible to reason about
the residual risk: a reader cannot tell whether an untested requirement is easy or hard, and
therefore cannot calibrate how much to trust the suite.

The first pass at the map also produced four false claims, because the mapping was derived by
matching requirement text against test *names* rather than by reading the test bodies. A
requirement about "reasoning effort" was marked covered by tests that exercised reasoning
*content*. This is the failure mode of any traceability map maintained by hand: it drifts toward
optimism, because a plausible-looking match is easier to record than a verified one.

## Decision

We adopt an explicit **coverage floor** and an explicit **tier taxonomy**, and we hold the map to
both.

### The floor

1. **Zero uncovered.** Every requirement and every invariant must be asserted by at least one
   test. A requirement with no test is a defect in the suite, not a fact about the requirement.
2. **At least 60% end-to-end.** At least 60% of requirements and at least 60% of invariants must be
   covered by *end-to-end* tests. Unit and frontend coverage counts **in addition to** the
   end-to-end floor, never instead of it. The end-to-end tier is the one that observes emergent
   behaviour across module seams, so it is the tier that carries the most weight per assertion.
3. **Consistent baseline, not impact triage.** Every backend subsystem and every user-visible
   frontend component receives a baseline test. The distribution of effort follows the shape of the
   codebase, not a ranking of which bugs would be most embarrassing. A low-traffic component with
   no test is a hole in the floor, not a lower-priority hole.
4. **The map is derived, not asserted.** The traceability map is regenerated from the collected
   test identifiers and the test bodies, never maintained by hand. A claim that a test covers a
   requirement is only recorded after reading the test.

### Test tiers

| Tier | Definition |
| --- | --- |
| **E2E** | Asserted through the public HTTP surface of the running harness. The only substitutions are the inference provider (the `steerable` scripted provider) and the container (the in-process stub sandbox). |
| **Frontend** | Asserted by rendering the *real* production component from `ui/src` to static markup. |
| **Unit** | Asserted at a module boundary, without the surrounding application. |
| **Config** | Asserted by validating repository configuration (`docker-compose.yml`, `run.sh`, the CI workflow). |

A requirement or invariant may be covered at more than one tier. The map records the *highest*
tier reached, and the report states the end-to-end count separately for green and non-strict
`xfail` tests so the headline number is never flattering.

### Non-strict `xfail` as a first-class outcome

A behaviour that is specified but not implemented is recorded as a non-strict `xfail` test whose
reason names the backlog entry tracking it. This is not a way to make the floor look green — the
report counts `xfail` separately from green end-to-end coverage — but it is a way to make an
unimplemented behaviour *visible* rather than absent. Implementing the behaviour flips the test to
passing without a test edit.

### Scope discipline

This work adds tests and test-only helpers. It does not change production code. Where a
behaviour can only be tested by first refactoring production code to expose a seam (for example,
extracting a pure reducer out of a React hook), the deep coverage is recorded as a backlog entry
rather than paid for with a production refactor.

## Consequences

### Positive

- The suite's residual risk becomes legible. A reader can see which behaviours are observed
  end-to-end, which are only observed at a module boundary, and which are not observed at all.
- The floor is a floor, not a target. It cannot be met by adding one test per requirement in the
  cheapest tier, because the end-to-end percentage is reported separately.
- The map is regenerated mechanically, so it cannot drift toward optimism the way a hand-written
  one did.

### Negative

- The floor is a floor, not a ceiling. Meeting it does not mean the suite is good; it means the
  suite is *consistent*. The report must be read as a baseline, not as a quality verdict.
- Some invariants are only reachable through a live container or a live Gitea instance. Those
  remain covered at a lower tier, or are gated behind the Docker-backed job, and the report says
  so explicitly rather than implying full coverage.
- The end-to-end suite grows. It must stay fast enough to run on every push, which constrains how
  much can be added per test and rules out live-container scenarios in the default job.

### Neutral

- No production behaviour changes. The only production-adjacent change is the CI workflow, which
  already runs the end-to-end and frontend suites.

## Alternatives considered

- **Prioritise by impact instead of spreading evenly.** Rejected: the user explicitly asked for a
  consistent baseline. Impact triage produces a suite that is excellent at the centre and absent
  at the edges, which is exactly the shape that makes residual risk uncalibratable.
- **Measure line coverage instead.** Rejected: line coverage rewards trivial getters and punishes
  declarative configuration, and it says nothing about whether a *behaviour* is observed. The
  requirement/invariant map is the unit of coverage that matters here.
- **Extract pure reducers from React hooks so the hooks can be tested deeply.** Rejected for now:
  it is a production refactor, and the task is explicitly test-only. The gap is recorded in the
  backlog instead.
- **Require 100% end-to-end coverage.** Rejected: several invariants are only observable against a
  live container or a live Gitea instance, and forcing 100% would mean either production changes
  or a suite that cannot run on every push.

## Provenance

- [0057-e2e-test-suite.md](./0057-e2e-test-suite.md) — the end-to-end suite and the first
  traceability map this decision generalises.
- [0056-steerable-model-provider.md](./0056-steerable-model-provider.md) — the scripted provider
  that makes deterministic end-to-end coverage possible.
- [test_coverage.md](../knowledge/test_coverage.md) — the generated traceability map and the
  undertested report.
- [REQ-052](../knowledge/requirements.md#req-052-deterministic-end-to-end-test-coverage-of-features-requirements-and-invariants)
- [INV-063](../knowledge/invariants.md#inv-063-deterministic-end-to-end-test-harness-isolation)
