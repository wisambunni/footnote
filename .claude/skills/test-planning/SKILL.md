---
name: test-planning
description: Designs test coverage for a feature or change — what to test, at which level, and what to deliberately skip. Also handles bug triage and release-readiness assessment. Use when planning tests before implementation, deciding whether coverage is sufficient to merge, or triaging a set of open bugs.
---

# Test planning

Design coverage. Do not write the implementation or run suites — those are
separate concerns.

## Choosing the level

Push tests to the lowest level that can actually catch the bug. Most teams
over-invest in integration tests that are slow and flaky and under-invest in
unit tests of the logic that actually breaks.

- **Unit** — pure logic, branching, edge cases, error paths. Fast, no I/O.
  This is where most coverage should live.
- **Integration** — the seams: handler to database, service to queue, module
  boundaries where the contract is easy to get wrong. Test the seam, not the
  logic on either side of it.
- **End-to-end** — critical user paths only. Every e2e test is a maintenance
  liability; justify each one.

For AWS-shaped code specifically:
- Extract handler logic into a plain function and unit test that. The Lambda
  handler itself should be a thin adapter with almost nothing to test.
- Test DynamoDB access against a local instance or moto, not mocks — mocked
  clients pass while real queries fail on key conditions.
- Test idempotency explicitly wherever redelivery is possible (SQS, Step
  Functions retries, EventBridge). A handler that has never been invoked twice
  in a test will fail the first time it happens in production.
- Assert on emitted events and messages, not just return values.

## Designing cases

For each unit of behavior, enumerate: the happy path, each error path, and the
boundaries (empty, single, many, maximum, null/undefined, malformed). Then ask
what a caller could do that the author did not anticipate.

Write assertions on behavior, not implementation. A test that asserts a mock
was called with specific arguments breaks on refactor and passes on real bugs.
Assert on what the caller observes.

Name tests for the condition and expected outcome, not the function under test.
`raises_when_quantity_exceeds_stock`, not `test_reserve_inventory_2`.

## What to skip

Say explicitly what is not worth testing and why. Generated code, thin
delegation, framework behavior, and third-party library internals are usually
not worth it. A plan that tests everything is a plan nobody follows.

## Bug triage

Classify each as severity (data loss > incorrect behavior > degraded > cosmetic)
crossed with frequency (all users, common path, edge case, single report). Fix
order follows the product of those, not the order reported. Note whether each
bug indicates a missing test — a bug that reached production through a tested
path means the test was wrong, which matters more than the bug.

## Release readiness

State a recommendation — ship, ship with known issues, or hold — and the
condition that would change it. List what is untested and what the exposure is
if it breaks. Do not express readiness as a coverage percentage; it measures
lines executed, not behavior verified.

## Output

Lead with the recommendation or the plan's shape, not preamble. Use a table for
test cases when there are more than a handful. Flag anything you would push
back on — coverage that looks thorough but tests the wrong level, or a release
gate that is theater.