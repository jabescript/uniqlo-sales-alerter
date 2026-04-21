# Changelog

All notable changes to the [Uniqlo Sales Alerter](https://github.com/kequach/uniqlo-sales-alerter) are documented in this file.

---

## v1.5.0 — 2026-04-21

### Improvements

- **Redesigned size filter controls** — clothing sizes are now checkboxes instead of a free-text input. Pants and shoe sizes use a dropdown that creates removable chips, matching the watched-variants interaction pattern. The underlying config format is unchanged.
- **Version visible in email footer and settings UI** — the email footer now reads "Sent by Uniqlo Sales Alerter v1.5.0" (version pulled from `pyproject.toml` at runtime). The settings page subtitle also shows the version (e.g. "Sales Alerter v1.5.0 — Settings").

### Bug fixes

- **Out-of-stock items no longer trigger notifications** — stock verification now uses the `CountryCapabilities.stock_api` mapping to decide behaviour per country. Countries with reliable stock data (`stock_api="v5"`) properly drop items when all sizes are out of stock. Countries with unreliable stock data (`stock_api="none"`, i.e. PH/TH) skip the stock call but still fetch L2 variant data to build accurate product URLs — items are never dropped for these countries.
- **PH/TH product URLs fixed** — Philippines and Thailand storefronts use a different URL format (`colorCode`/`sizeCode` without a price-group path segment). A new `url_style` capability drives `build_product_url` so each country gets the correct format. URL parsing (`parse_uniqlo_url`, variant keys, settings UI) now handles both formats.
- **PH missing sale items** — added `v3_ltd` (limitedOffer) to PH's `listing_sources` so the full sale catalogue is retrieved, not just the `discount` flagged items.

### New features

- **Per-variant stock count in every notification** — console, email, Telegram, and the HTML report now show the exact number of units remaining next to each size chip (e.g. `M (12)`). The data comes from the v5 stock API that was already being called for in-stock filtering.
- **Low-stock badge** — variants whose quantity is at or below a configurable threshold are marked `(3, low stock)` and styled in red in each channel. The user threshold is authoritative when positive; set it to `0` to fall back to the Uniqlo API's own `LOW_STOCK` flag as the sole signal.
- **Opt-in low-stock alert suppression** — a new `notifications.suppress_low_stock_alerts` toggle keeps low-stock variants out of the seen-set so they don't fire an alert. The typical use case: an out-of-stock item restocks with only 2 units while your threshold is 3 — normally that would retrigger a notification, but with the toggle on it's quietly deferred until the quantity climbs back above the threshold. Low-stock sizes still appear inside other notifications so you see the full state of a deal.
- **Product rating** — when the Uniqlo API exposes reviews, notifications now include a `★ 4.3 (127 reviews)` line below the product title.
- **New "Notification Triggers" settings section** — sits between *Schedule* and *General* in the web UI. Contains the low-stock threshold (default 3) and the opt-in re-alert toggle (default off).

### Config

- New `notifications.low_stock_threshold` (int, default `3`) and `notifications.suppress_low_stock_alerts` (bool, default `false`) in `config.yaml`.
- New env vars `NOTIFY_LOW_STOCK_THRESHOLD` and `NOTIFY_SUPPRESS_LOW_STOCK_ALERTS`.
- New fields `SaleItem.stock_quantities` and `SaleItem.stock_statuses` (parallel to `available_sizes`); safe to ignore for consumers that don't need them.

### Improvements

- **HTML report: inline stock counts** — stock counts now render inside the size chip as subtle secondary text instead of as a separate badge. Low-stock chips get a filled red background so they stand out without extra visual clutter.
- **Quieter INFO logs** — demoted 16 verbose or redundant log lines to DEBUG across config, dispatcher, email, sale checker, and Uniqlo client. A typical sale-check cycle now produces ~3 INFO lines (fetch summary, result, delivery) instead of ~10. Internal details like notifier registration, state file loading, quiet-hour skips, and per-endpoint pagination totals are still available at DEBUG level. APScheduler's per-job "executed successfully" messages are also suppressed.
- **Settings UI log timing** — the "Settings UI: ..." message now appears at the end of lifespan startup (right before uvicorn starts serving) instead of before `uvicorn.run()` begins.
- **Favicon** — the settings UI and HTML report pages now show an inline SVG price-tag icon in the browser tab.

### Code quality

- **Telegram test coverage** — added three new test classes: `TestEscapeMd` (MarkdownV2 escape helper), `TestTelegramCaptionMarkdownV2` (validates caption output for all price display states, catches double-escape bugs), and `TestTelegramNotifierSend` (mocked Bot API covering send\_photo/send\_message, empty deals, error resilience, inline keyboard buttons for watch/unwatch/ignore, and server\_url toggle).
- **Test consolidation** — reduced test suite from 221 to 201 tests by extracting cross-channel consistency tests (color labels, watched badges, unknown discount display), parametrizing repetitive patterns (`TestCoerce`, `TestDeepMerge`, `TestVariantKeys`, enabled/disabled checks), and merging overlapping assertions. No coverage removed.
- **Architecture refactor** — DRY: shared price/colour/image helpers in `notifications/base.py`, unified pagination (`_paginate`), single `build_product_url`. Replaced global `state` with FastAPI `Depends()` injection. Split `_build_report` into `_render_card` + `_REPORT_CSS`. Added `html.escape()`, narrowed broad `except` blocks, aligned v3/v5 logging.
- **End-to-end test** (`test_e2e_html_preview.py`) — new test suite that hits the live Uniqlo API, runs the full sale-check pipeline, generates an HTML report, and cross-verifies: every deal has required fields, valid product URLs with correct query params, consistent discount percentages, and that the report faithfully includes all deal names, prices, sizes, and action links. Also spot-checks that product IDs and page URLs resolve in the real API. Skips gracefully when the API is unreachable.

### Docs

- **README**: expanded the old *Notification modes* section into a richer *How notifications are triggered* walkthrough covering first-seen, size restocks, OOS silent-drops, restock re-fires, discount changes, quantity fluctuations, and the new opt-in low-stock crossing. Added the full variant-key format and a PH/TH caveat.

### Bug fixes

- **Wrong product image for colour variants** — when stock verification picked a colour not present in the listing API's image map, notifications fell back to the representative colour's image (e.g. showing a black jacket instead of the off-white one linked in the product URL). `resolve_color_image` now derives the correct image URL from the Uniqlo CDN naming pattern when the exact colour code is missing from the map. Removed unused `image_url_for_color` from `UniqloProduct` (superseded by `resolve_color_image`).
- **YAML comments preserved on save** — `save_config` was stripping comments that appear between block sequences and the next mapping key (e.g. "# Ignored products…", "# Server URL…"). ruamel.yaml stores these on the last sequence item's internal comment attributes; the merge logic now transplants them to the replacement sequence.
- **`watched_urls` no longer reappears in config.yaml** — the legacy migration field was included in `model_dump()` output, causing `save_config` to write `watched_urls: []` back on every save. Fixed with `exclude=True` on the Pydantic field.

---

## v1.4.0 — 2026-04-17

### Docs

- **README**: restructured for compactness — merged Web UI into Quick Start, collapsed secondary install paths and deployment sections into expandable blocks, merged watched/ignored and scheduling/quiet-hours into combined sections, promoted Notifications to a top-level section, and trimmed redundant prose throughout (~720 lines down to ~430).
- **config.yaml**: reordered to match the README and web UI structure — general filters (gender, sizes, min discount) now come before watched/ignored items, added section divider comments, trimmed verbose comments, removed legacy `watched_urls` key.

### New features

- **Colour in notifications** — all notification channels now display the colour name resolved from the Uniqlo API for each deal.
  - **Email**: each colour+size variant is a separate listing with its colour, a direct link, and a single "Watch" action (instead of grouping all sizes into one row with multiple Watch links).
  - **Telegram**: colour line shown between the product name and price in the caption.
  - **HTML report**: colour label displayed below the product title in each card.
  - **Console**: colour line printed after the price.
- **Configurable port** — new `port` setting (default `8000`) controls which port the server listens on. `server_url` is now host-only (e.g. `http://192.168.1.50`); the port is appended automatically. Configurable via `config.yaml`, the web UI, or the `PORT` environment variable.
- **Unwatch button** — watched items now show an "Unwatch" action button (instead of "Watch") in all notification channels. Clicking it removes the product from the watch list. New endpoint: `GET /actions/unwatch/{id}`.
- **Settings link in notifications** — when `server_url` is configured, all notification channels include a link to the settings page in their footer.
- **Clickable product images** — product images in email and HTML report notifications now link directly to the variant's product page on uniqlo.com.
- **Colour-matched product images** — notification images now match the variant's colour instead of always showing the product's default colour. Applies to email (per-variant), Telegram (first variant's colour), and HTML report (first variant's colour).
- **Scheduled checks** — new `scheduled_checks` setting for fixed daily check times (e.g. `["12:00", "18:00"]`). Runs independently of `check_interval_minutes` and is **not** affected by quiet hours. Both modes can be used together. Configurable via `config.yaml`, the web UI, or the `SCHEDULED_CHECKS` environment variable. The web UI now shows periodic and scheduled checks side by side. When both modes are active, a recent scheduled check automatically skips the next periodic one.
- **Disable periodic checks** — setting `check_interval_minutes` to `0` disables periodic checks entirely, allowing scheduled-check-only operation.
- **Check on startup toggle** — new `check_on_startup` setting (default `true`) controls whether a sale check runs immediately when the server starts. Set to `false` to skip the initial check and wait for the first scheduled or periodic check. Configurable via `config.yaml`, the web UI, or `CHECK_ON_STARTUP` env var.

### Bug fixes

- **Watched items no longer show a false "Sale" label** — watched items not on sale previously displayed a "Sale" badge because the pricing logic conflated "no promotion" with "unknown discount". The `has_known_discount` flag is now determined by whether the item came from the sale feed rather than by the `promo` field, which correctly handles Singapore (where sale items have `promo=None`) and watched-only items alike. Verified against all 22 supported countries via a full API sweep.
- **SEA stores (PH, TH) no longer drop all items** — the v5 stock endpoint returns `STOCK_OUT` for all variants of v3-sourced products, causing stock verification to drop every item. When all stock entries report OOS, the verifier now uses v5 L2 data to rebuild correct URLs with real colour codes instead of silently discarding items.
- **Country capabilities registry** — a new `CountryCapabilities` data structure in `config.py` maps each of the 22 supported countries to its API profile (which listing endpoints to query, whether stock verification is reliable, whether pricing is limited). `fetch_sale_products()` now only calls the endpoints that actually return data for the configured country, eliminating redundant cross-version API calls. Determined via a full probe of all 22 countries.

### Code quality

- Consolidated test boilerplate: parametrized SMTP error tests, extracted `EmailChannelConfig` factory, reused `sample_deal` in variant-key and stock-verification tests, hoisted shared imports, deduplicated mock helpers.
- Codebase clean code pass: extracted `_STOCK_OUT` / `_DEFAULT_PRICE_GROUP` constants, added docstrings to Pydantic models and formatter functions, renamed unclear variables (`t` to `safe_title`), unified duplicate `print` + `logger` rate-limit messages in `UniqloClient`.

---

## v1.3.0 — 2026-04-17

### New features

- **Ignore list** — hide products from all results regardless of sale status, colour, or size. Configurable via `config.yaml` (`filters.ignored_products`), the web UI, environment variable (`FILTER_IGNORED_IDS`), or notification action buttons. Watched variants take precedence over ignored products.
- **Watched variants** — replaced `watched_urls` (plain URL strings) with structured `watched_variants` entries. Each entry stores the full product URL; product ID, colour, size, and price group are parsed automatically.
- **Metadata enrichment** — on startup the server resolves human-readable metadata from the Uniqlo API: product names, colour names (e.g. "09 Schwarz"), and size names (e.g. "M"). Enriched data is persisted to `config.yaml` so it survives restarts. Ignored product names are also resolved.
- **Server URL & action buttons** — new `server_url` config option. When set, every notification includes Ignore and per-size Watch buttons:
  - **HTML report**: star icon (☆) next to each size chip to watch that variant; Ignore button below.
  - **Telegram**: inline keyboard with one "Watch {size}" button per available size, plus "Ignore".
  - **Email**: per-size "Watch {size}" links and an "Ignore" link in each deal row.
  - **Console**: clickable action URLs printed below each deal.
- **Product verification** — adding a product to the watch or ignore list (via web UI or action buttons) verifies it exists in the Uniqlo catalogue before saving. Invalid IDs show an error.
- **Auto-save** — adding or removing watched variants and ignored products in the web UI saves immediately and shows a confirmation toast. No need to click "Save & Reload".
- **Mobile-responsive settings UI** — the settings page now adapts to small screens with stacked layouts, full-width buttons, and proper word wrapping.

### Deprecated

- **`watched_urls`** — replaced by `watched_variants`. Existing entries (in `config.yaml` or via `FILTER_WATCHED_URLS` env var) are automatically migrated on startup. The field is kept for backward compatibility but will be removed in a future version.

### Web UI

- Watched variants section: shows product name, ID, colour name, size name, and a clickable link to the product page. Paste a URL to add.
- Ignored products section: shows product name and ID with a clickable link. Accepts a product URL or plain ID.
- Server URL input with guidance for localhost and LAN setups.

### Preview mode

- `--preview-cli` and `--preview-html` now start the full server instead of exiting after one check. This keeps action buttons functional in the generated report.

### Code quality

- Extracted shared helpers to eliminate duplicated code across scheduler, routes, sale checker, and settings UI.
- Replaced cryptic variable names across the codebase for readability.
- Extracted shared constants: `PROJECT_URL`, `_HTTP_FAILURE_PARAMS`, `_DEFAULT_CURRENCY`.
- Added `SaleChecker.http_client` public property; production code no longer accesses the private client field.
- HTML escaping (`html.escape`) on all user-controlled text in action confirmation pages.
- Improved error handling: state file corruption is now logged; misleading v3 API log corrected.
- Removed redundant regex validation on quiet hours fields.
- Deduplicated secret-path traversal in API routes.

### New API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/products/{id}/verify` | Check if a product exists in the Uniqlo catalogue |
| `GET` | `/actions/ignore/{id}` | Add a product to the ignore list (browser action) |
| `GET` | `/actions/watch/{id}` | Add a variant to the watch list (browser action) |

---

## v1.2.0 — 2026-04-15

### New features

- **Quiet hours** — suppress all API calls and notifications during a configurable daily time window (e.g. 01:00–08:00). Uses local system time. Supports midnight crossover (e.g. 23:00–06:00). Configurable via `config.yaml`, web UI, or environment variables (`QUIET_HOURS_ENABLED`, `QUIET_HOURS_START`, `QUIET_HOURS_END`).

### Web UI

- Quiet hours toggle and time inputs added to the API Settings section.
- Sale category paths moved to its own section with "(Singapore only)" label in the header.

---

## v1.1.0 — 2026-04-14

### New features

- **Web UI** — built-in settings page at `/settings` for viewing and editing the entire configuration in the browser. Covers all settings: country, check interval, gender/size filters, watched URLs, notification modes, and Telegram/email channels. Changes are saved to `config.yaml` (preserving comments) and applied immediately — no restart required.
- Secret fields (bot token, SMTP password) are masked in the UI; submitting `***` preserves the existing value.

### Improvements

- Clearer descriptions for watched products in the configuration.
- Removed `.env` file in favour of `config.yaml` and environment variables.

---

## v1.0.0 — 2026-04-13

### Features

- Monitors Uniqlo sales by querying the internal Commerce API (no browser automation or scraping).
- Fetches from multiple API versions and flag codes in parallel for comprehensive coverage.
- **Filters**: gender (men, women, unisex, kids, baby), minimum discount percentage, clothing/pants/shoes/one-size filters.
- **Watched products**: track specific product URLs regardless of sale status; notified on restock, new sizes, sale, or discount changes.
- **Notification channels**: Telegram (photo messages with inline size links) and email (HTML with product images, prices, and direct links).
- **Notification modes**: `all_then_new` (default), `new_deals` (persistent state across restarts), `every_check`.
- Real-time stock verification per colour/size variant — only in-stock sizes are shown, with the highest-quantity colour selected.
- Direct product URLs with correct colour and size display codes for one-click purchase.
- CLI preview (`--preview-cli`) and HTML report preview (`--preview-html`) for local testing without sending notifications.
- REST API with interactive Swagger docs at `/docs`.
- Docker support with multi-arch images (`linux/amd64`, `linux/arm64`) on Docker Hub.
- Docker Compose and `docker run` quickstart.

### Supported countries

- **Full support** (17 countries): Germany, UK, France, Spain, Italy, Belgium (FR/NL), Netherlands, Denmark, Sweden, Australia, India, Indonesia, Vietnam, Philippines, Malaysia, Thailand.
- **Limited support** (5 countries): US, Canada, Japan, South Korea, Singapore — sale-flagged items shown with current price and "Sale" label; discount percentage unavailable.

---

## v0.1.0 — 2026-04-08 – 2026-04-11

Initial development.

- First draft of the sale checker, notification dispatcher, and Uniqlo API client.
- Basic README with setup instructions.
- Email notification screenshots.
- Germany-only support.
