# Codex Feature Request Template

Use this template when starting a new Codex thread for Uniqlo Sales Alerter
feature work. Start the thread from the repository root so repo-scoped skills,
agents, and `AGENTS.md` are visible.

For token efficiency, use the smallest prompt that matches the risk. Tiny tasks
should rely on automatically loaded `AGENTS.md`; use the workflow skill for
material work where the extra context is worth it.

## Tiny Or Low-Risk Prompt

Use this for typos, small docs edits, obvious one-file fixes, or focused test
adjustments where no integration surface is likely to change.

```text
Small fix:
<Describe the task in one or two sentences.>

Follow AGENTS.md only. Keep context narrow, read only the relevant files first,
and use rg to locate references. Do not invoke $uniqlo-change-workflow, read
workflow docs, or spawn subagents unless you find material risk. Run the focused
check that proves the change.
```

## Standard Feature Prompt

Use this for material feature work, nontrivial bug fixes, and changes that need
the repo's full plan/spec/verify/review loop.

```text
$uniqlo-change-workflow

Feature request:
Add <feature>.

Goal:
<Describe the user-visible behavior that should exist when this is done.>

Non-goals:
<List behavior, refactors, providers, countries, config, or release work that
should not be changed.>

Token mode:
- Keep context narrow; use rg and read only relevant files first.
- Do not spawn reviewers unless the diff is material.
- Use uniqlo-integration-reviewer only when the touched surface matches its
  integration-risk scope.
- Summarize long command output instead of pasting logs.

Important constraints:
- Follow AGENTS.md and docs/CODEX_WORKFLOW.md.
- Keep the implementation narrow and consistent with existing Python, FastAPI,
  Pydantic, httpx, notification, config, and pytest patterns.
- Do not add browser automation, scraping outside the existing API approach,
  new notification providers, new persistence formats, new services, new
  dependencies, MCP, A2A, or extra agents unless you explain why and ask first.
- Use the router-first workflow: the main Codex agent implements and only
  escalates to specialist reviewers when risk or task complexity warrants it.

Acceptance checks:
- <Concrete behavior 1>
- <Concrete behavior 2>
- <README/config/changelog expectation, if any>

Verification:
Run the narrowest meaningful checks first, then broaden according to
docs/CODEX_WORKFLOW.md. Prefer behavior-oriented tests; use mocks for external
boundaries, not for the logic being proved. After implementation, spawn the
appropriate review agent before finalizing if the diff is material.
```

## Integration-Sensitive Feature Prompt

Use this when the change touches Uniqlo API retrieval, stock verification,
filtering, CountryCapabilities, product URLs, notifications, config
persistence, secrets, Docker, or release behavior.

```text
$uniqlo-change-workflow

Feature request:
Add <feature>.

Goal:
<Describe the desired behavior and affected countries, channels, or deployment
mode.>

Non-goals:
<List countries, notification channels, config keys, Docker behavior, or release
work that should stay unchanged.>

Integration-sensitive surfaces:
- <Uniqlo API / stock / filtering / CountryCapabilities / URLs / notifications /
  config / secrets / Docker / release>

Token mode:
- Keep context narrow; read only the relevant API, config, notification, tests,
  and docs files first.
- Use exactly the listed reviewers; do not spawn extra agents unless a new
  concrete risk appears.
- Summarize long command output instead of pasting logs.

Important constraints:
- Follow AGENTS.md and docs/CODEX_WORKFLOW.md.
- Preserve sale coverage and avoid hardcoded country checks.
- Keep notification channels aligned when notification content changes.
- Preserve YAML comments, env var docs, secret masking, and config reload
  semantics when config changes.
- Do not add new dependencies, services, MCP, A2A, dynamic registries, or extra
  agents without asking first.

Acceptance checks:
- <Concrete behavior 1>
- <Concrete behavior 2>
- <Representative country/channel/config check>

Verification:
Run focused tests first. Run Ruff and the relevant pytest suite. If data
retrieval, filtering, CountryCapabilities, listing_sources, stock verification,
or URL construction changes, run the live e2e check from docs/CODEX_WORKFLOW.md
or explain why it could not run. Avoid over-mocked tests that would pass while
the real API, filtering, URL, notification, config, or state behavior is broken.

Review routing:
Spawn uniqlo-code-reviewer for material diffs. Also spawn
uniqlo-integration-reviewer for this integration-sensitive change. Summarize
findings and fix confirmed issues before finalizing.
```
