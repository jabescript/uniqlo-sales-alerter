# Codex Workflow

This guide defines the default agent-assisted software engineering workflow for
Uniqlo Sales Alerter. It keeps Codex quick for small fixes and disciplined for
changes that can affect sale coverage, notifications, config/state, Docker, or
release quality.

## Default Loop

1. **Scope**
   - State the goal, non-goals, constraints, and "done when" checks.
   - Mention relevant files, failing tests, logs, screenshots, config examples,
     or API symptoms when known.
   - For one-line or obvious fixes, go straight to implementation.

2. **Explore And Plan**
   - For ambiguous or multi-file changes, start in plan mode or ask Codex to
     explore before editing.
   - Let Codex read the relevant app, test, docs, config, and CI files.
   - Produce a short plan with affected files and verification commands.

3. **Use A Lightweight Spec**
   - For material work, keep a brief spec in the thread or task document:
     goal, non-goals, acceptance checks, risks, and task list.
   - This is the useful part of OpenSpec-style work: agree on behavior before
     writing code without adding ceremony to small edits.
   - If the team later adopts OpenSpec itself, map this loop to
     `explore -> propose -> apply -> archive`.

4. **Implement Narrowly**
   - Follow existing Python, FastAPI, Pydantic, httpx, notification, config,
     and pytest patterns.
   - Prefer small, reviewable changes over broad refactors.
   - Do not add browser automation, new notification providers, new persistence
     formats, new services, or new dependencies without explicit approval.

5. **Verify With Evidence**
   - Run the narrowest meaningful checks first, then broaden as risk grows.
   - Report exact commands and outcomes in the final response.
   - If live API, network, Docker, or environment access blocks a check, say so.

6. **Fresh-Context Review**
   - For material changes, ask Codex to spawn `uniqlo-code-reviewer`.
   - For Uniqlo API, stock, country capability, URL, notification, config,
     secret, Docker, release, or state changes, also spawn
     `uniqlo-integration-reviewer`.
   - Treat subagent findings as review input, not as a replacement for tests.

7. **Docs And Changelog**
   - Update README for user-facing behavior, config, API, notification, Docker,
     or CLI changes.
   - Preserve and update comments in `config.yaml` when keys change.
   - Update `CHANGELOG.md` only when the repo rules require it for the current
     version; do not add release-note noise for internal workflow-only changes.

## When To Use Each Codex Surface

- **Prompt/thread context:** one-off task constraints and task-specific
  decisions.
- **`AGENTS.md`:** durable repo rules, architecture constraints, verification,
  and documentation expectations.
- **`.codex/agents/`:** focused project subagents for review and integration
  risk.
- **`.agents/skills/`:** repeatable workflows that should be reusable across
  Codex sessions.
- **`.codex/config.toml`:** repo-scoped Codex settings such as bounded subagent
  fan-out.
- **Worktrees:** parallel or background tasks where edits should not collide
  with the main checkout, `config.yaml`, or `.seen_variants.json`.

## Agent Topology Decisions

These decisions adapt multi-agent architecture principles to this repo without
adding platform complexity.

- **Router first:** the main Codex agent handles normal scoping,
  implementation, verification, and final synthesis.
- **Specialists on demand:** route material diffs to `uniqlo-code-reviewer`.
  Add `uniqlo-integration-reviewer` only for API, stock, filtering,
  CountryCapabilities, URL, notification, config, secret, Docker, or release
  risk.
- **Supervisor only when needed:** use supervisor-style coordination only for
  multi-step work where separate specialist reviews must be sequenced or
  reconciled. Most tasks should need one main agent and at most one reviewer.
- **Repo-local graph, not decentralized mesh:** keep the workflow inside this
  repository with direct child subagents. Do not introduce A2A protocols,
  dynamic agent registries, external orchestration services, or extra MCP
  servers for routine development.
- **Agent cards as contracts:** each `.codex/agents/*.toml` file is the
  practical agent card: name, role, capabilities, trigger conditions, required
  context, and output format.
- **MCP boundary:** use MCP only when an external tool or data source is
  genuinely needed; do not use it as the normal communication layer between
  repo-local Codex agents.

## Project Subagents

Use these explicitly when the task warrants it:

```text
Spawn uniqlo-code-reviewer to review the current diff for correctness,
regressions, missing tests, architecture issues, scope drift, and docs/changelog
gaps. Wait for the result and summarize findings before finalizing.
```

```text
Spawn uniqlo-integration-reviewer to review this change for Uniqlo API
coverage, CountryCapabilities, stock verification, product URLs, notification
alignment, config persistence, secrets, Docker behavior, and missing e2e checks.
```

Good review prompts name the plan, changed files, and what counts as a finding.
Ask reviewers to flag correctness, coverage, integration, security, data-loss,
and verification gaps rather than style preferences.

## Verification Matrix

Use the smallest check that proves the change, then broaden when the touched
surface is shared or risky.

- Normal code changes: `python -m ruff check src/ tests/` and
  `python -m pytest tests/ --tb=short`.
- Module-specific changes: start with focused tests, then run the full local
  suite above.
- Uniqlo API, stock, filtering, CountryCapabilities, listing_sources, or URL
  construction changes: also run
  `python -m pytest tests/test_e2e_html_preview.py -m e2e -v --tb=short`.
- Notification changes: verify all affected channels stay aligned; use focused
  notification tests and preview/manual checks when output layout changes.
- Config/settings changes: test config loading/saving, README/env var docs,
  YAML comment preservation, and secret masking/redaction.
- Docker/release changes: verify build/runtime commands and README examples.
- Test quality: prefer observable behavior over implementation call assertions.
  Mock external network, time, filesystem, or service boundaries when useful,
  but do not mock away the code path the change is meant to prove.

## Failure Patterns To Avoid

- Long kitchen-sink threads mixing unrelated tasks.
- Specs that drift away from code without verification.
- Chasing every subagent nit instead of correctness and requirement gaps.
- Trusting generated tests that only mirror the implementation.
- Over-mocked tests that would still pass if the real parsing, filtering,
  URL, notification, config, or integration path were broken.
- Running live e2e for every small change; reserve it for the API/integration
  surfaces named above.
- Updating `CHANGELOG.md` for purely internal workflow-only changes.
