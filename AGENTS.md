# Codex Guardrails

These rules are derived from `.cursor/` and `.github/` project instructions and
apply to the whole repository.

## Verification

- When code in `src/` or `tests/` changes, run `python -m ruff check src/ tests/`
  and `python -m pytest tests/ --tb=short` before finishing. Fix failures when
  they are caused by the change. For documentation-only edits, these checks are
  optional.
- If the environment blocks full verification, run the narrowest meaningful
  checks and report the blocker clearly.
- For changes touching Uniqlo data retrieval, stock verification, filtering,
  `CountryCapabilities`, `listing_sources`, or product URL construction, also
  run `python -m pytest tests/test_e2e_html_preview.py -m e2e -v --tb=short`.

## Documentation

- Update `README.md` for user-facing behavior changes, including new config
  options, CLI flags, API endpoints, notification format changes, or Docker
  examples.
- When modifying `config.yaml`, add or preserve comments that explain any new
  or changed keys and list supported option values where applicable.
- Update `CHANGELOG.md` under the current version from `pyproject.toml` for
  user-visible source changes. Do not invent a new version number.
- When updating the changelog, update the current version header date to the
  current date using `## vX.Y.Z - YYYY-MM-DD`.
- If fixing a bug introduced in the current unreleased version, edit the
  existing changelog entry for that feature instead of adding a new `Fixed`
  entry.

## Architecture

- Use `config.capabilities` and the `CountryCapabilities` registry for
  country-specific behavior. Do not hardcode country checks such as
  `if country == "ph"`.
- Keep price display logic consistent across all notification channels:
  known discount with percentage, unknown discount as `Sale`, and known zero
  discount as plain price.
- `has_known_discount` is based on whether the item came from the sale feed,
  not on the `promo` field alone.
- Stock behavior is controlled by `CountryCapabilities.stock_api`. Countries
  with `stock_api="none"` skip the stock call but still fetch L2 data for URLs.
- Product URL format is controlled by `CountryCapabilities.url_style`; use
  `build_product_url` rather than rebuilding country-specific URLs manually.
- Keep email, Telegram, console, and HTML report notifications aligned in data,
  price logic, action buttons, and footer settings links.

## Python Style

- Prefer descriptive names. Domain abbreviations `pid`, `pg`, and `wv` are OK.
- Extract magic values to module-level constants and use `frozenset` for
  immutable valid-value sets.
- Public classes and functions need docstrings. Private helpers need docstrings
  when their purpose is not obvious.
- Comments should explain why, not narrate what the code does.
- Use `logger` for diagnostics. `print()` is acceptable only for intentional
  user-facing console output.
- Prefer specific exception types over bare `except Exception`.
- In Pydantic models, use `Field(default_factory=...)` for mutable defaults.

## Tests

- Use `sample_deal(**overrides)` from `tests/conftest.py` for `SaleItem`
  objects in tests.
- Use `_make_email_cfg(**overrides)` for notification email config tests.
- Use `noop_verify()` and `noop_watched_fetch()` to isolate sale-checker tests
  from stock verification and watched-product fetching.
- Use `_mock_v3_empty()` from `test_uniqlo_client.py` for v3 endpoint mocks.
- Prefer behavior-oriented tests that exercise real normalization, filtering,
  notification, URL, and config behavior. Mock external network/service
  boundaries, but do not mock away the logic the test is meant to prove.
- For `fetch_sale_products` tests, choose countries whose capabilities match
  the endpoint under test: `de/de`, `id/en`, `th/en`, or `sg/en` with
  `sale_paths`.
- When adding countries, update e2e representatives only if the capabilities
  introduce a new `listing_sources x stock_api x url_style` combination.
- Parametrize when three or more tests follow the same pattern.

## Config And Settings

- `server_url` is host-only; `port` is separate. Use `config.full_server_url`
  when a combined URL is needed.
- The settings UI auto-saves watched variants and ignored products immediately;
  other settings require Save & Reload.

## Codex Operating Workflow

- For material feature, bug, refactor, API retrieval, filtering, notification,
  config, settings UI, Docker, release, or developer workflow changes, follow
  `docs/CODEX_WORKFLOW.md`.
- Start hard or ambiguous work in plan mode, or explicitly ask for an
  exploration-and-plan pass before edits. Skip this ceremony for obvious
  one-line fixes.
- Use a lightweight spec-first loop for material changes: goal, non-goals,
  affected files, acceptance checks, task list, implementation, verification,
  fresh-context review, and docs/changelog decision.
- Keep one Codex thread per task. Clear or start fresh after repeated failed
  corrections or when switching to unrelated work.
- Prefer worktree isolation for parallel/background tasks so generated edits do
  not collide with the main checkout or local config/state files.
- Use the repo-local router-first topology from `docs/CODEX_WORKFLOW.md`: the
  main Codex agent routes normal work and escalates to specialist review only
  when risk or task complexity warrants it.
- Use project-scoped subagents when their focused context helps:
  - `uniqlo-code-reviewer`: fresh-context review of diffs for correctness,
    Python/FastAPI architecture, regressions, scope drift, and missing tests.
  - `uniqlo-integration-reviewer`: focused review for Uniqlo API behavior,
    country capabilities, notifications, config persistence, secrets, Docker,
    and live e2e verification risk.
- Invoke `$uniqlo-change-workflow` for repeatable feature, bug, refactor,
  API/filtering, notification, config, docs, release, or workflow tasks.
- Always include command evidence or explain why a check could not be run.
- Do not use subagents as a replacement for tests or human review; use them to
  find gaps before the final response or PR.
- Do not add new agents, MCP servers, A2A-style protocols, or external
  orchestration for this repo unless there is a repeated need that cannot be
  handled by the existing skill, reviewer agents, and verification loop.
