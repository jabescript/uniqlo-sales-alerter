# Changelog

All notable changes to the [Uniqlo Sales Alerter](https://github.com/kequach/uniqlo-sales-alerter) are documented in this file.

---

## v1.4.0 — 2026-04-17

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
- **Scheduled checks** — new `scheduled_checks` setting for fixed daily check times (e.g. `["12:00", "18:00"]`). Runs independently of `check_interval_minutes` and is **not** affected by quiet hours. Both modes can be used together. Configurable via `config.yaml`, the web UI, or the `SCHEDULED_CHECKS` environment variable. The web UI now shows periodic and scheduled checks side by side.

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
