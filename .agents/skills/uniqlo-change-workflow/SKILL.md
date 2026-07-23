---
name: uniqlo-change-workflow
description: Use for Uniqlo Sales Alerter feature work, bug fixes, refactors, API/filtering/country capability changes, notification changes, config/settings UI changes, Docker/release work, docs, and developer workflow changes that need the repo's plan/spec/verify/review loop.
---

# Uniqlo Change Workflow

Use this skill to keep material Uniqlo Sales Alerter changes scoped, verified,
and reviewable without adding ceremony to small edits.

## 1. Load The Local Contract

Before editing, read the relevant parts of:

- `AGENTS.md`
- `docs/CODEX_WORKFLOW.md`
- `pyproject.toml`
- The files directly involved in the requested change
- Existing `.cursor/rules/` only when you need extra detail behind AGENTS.md

If the request touches Uniqlo API retrieval, stock verification, filtering,
country capabilities, product URLs, notifications, config persistence, secrets,
Docker, or release behavior, treat it as integration-sensitive.

## 2. Scope Before Editing

For material changes, write a short plan in the thread:

- Goal
- Non-goals
- Files likely to change
- Acceptance checks
- Test/verification commands
- README/config/changelog impact

Ask one concise clarifying question only when a wrong assumption would create
user-visible behavior, broken notifications, lost config/state, leaked secrets,
or release risk.

## 3. Implement Narrowly

Follow existing Python, FastAPI, Pydantic, httpx, notification, config, and
test patterns. Keep changes close to the requested behavior. Do not add browser
automation, scraping outside the existing API approach, new notification
providers, new persistence formats, new network services, or new dependencies
without explicit user approval.

## 4. Route Specialist Review Intentionally

Use a repo-local, router-first topology:

- The main Codex agent owns implementation and decides whether focused review
  is needed.
- For most material diffs, route once to `uniqlo-code-reviewer`.
- Add `uniqlo-integration-reviewer` only for API, stock, filtering,
  CountryCapabilities, URL, notification, config, secret, Docker, or release
  risk.
- Treat each subagent TOML as the agent card: it defines the agent's role,
  capabilities, required context, and expected findings format.
- Keep subagents as direct children. Do not introduce MCP, A2A, registries, or
  extra orchestration for normal repo work.

Use supervisor-style coordination only when a task has multiple dependent
review streams that must be synthesized before finalizing.

## 5. Verify With Evidence

Run the narrowest meaningful checks first. Prefer this order:

1. Focused tests for the touched module.
2. `python -m ruff check src/ tests/`
3. `python -m pytest tests/ --tb=short`
4. `python -m pytest tests/test_e2e_html_preview.py -m e2e -v --tb=short`
   when the change touches data retrieval, stock verification, filtering,
   CountryCapabilities, listing_sources, or product URL construction.
5. Docker/manual preview checks only when deployment, CLI, preview, or runtime
   behavior changed.

Before treating new tests as evidence, check that they assert observable
behavior and would fail if the changed logic were broken. Use mocks for external
network/service boundaries, not for the code path being proved.

Report exact commands and results. If a check cannot run, explain why.

## 6. Review Before Finalizing

For material changes, spawn `uniqlo-code-reviewer` for a fresh-context diff
review. For integration-sensitive changes, also spawn `uniqlo-integration-reviewer`.
Fix confirmed findings, then rerun relevant checks.

Update README, config comments, and CHANGELOG.md only when the repo rules say
the change affects users, config, notifications, API, Docker, or release notes.
