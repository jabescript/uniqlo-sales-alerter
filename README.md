# Uniqlo Sales Alerter

A Python web server that monitors [Uniqlo](https://www.uniqlo.com) sales and notifies you when items match your criteria. It talks directly to Uniqlo's internal Commerce API — no browser automation or scraping required.

## Features

- **Periodic sale monitoring** — polls the Uniqlo catalogue on a configurable interval
- **Configurable filters** — gender, minimum discount %, clothing/pants/shoe sizes (verified against real-time stock per variant), watched product URLs (notified whenever in stock, even without a sale)
- **Preview modes** — CLI (terminal text) or HTML (visual report with product images in the browser)
- **Pluggable notifications** — Telegram (with product images), Email (HTML), extensible to Discord/Slack/etc.
- **REST API** — query current deals, trigger manual checks, view configuration (interactive docs at `/docs`)

## How it works

The server reverse-engineers Uniqlo's internal Commerce API (the same one their website's SPA uses). On each check it:

1. Fetches only sale items via `flagCodes=discount` with pagination (100 items per page), avoiding the full catalogue.
2. Verifies each item has a promo price lower than the base price.
3. Computes the discount percentage and applies your configured filters (gender, sizes, min discount %).
4. **Verifies real-time stock per variant** — for each matching product, fetches the stock endpoint to check which colour×size combinations are actually purchasable online. Sizes that are out of stock are excluded. Products where all matching sizes are sold out are dropped entirely.
5. Generates **direct variant URLs** pointing to an **in-stock colour** for each matching size (e.g. `…/E479257-000/00?colorDisplayCode=07&sizeDisplayCode=004`). The colour with the highest stock quantity is preferred, so links lead to purchasable variants.
6. Caches the results for fast API responses.
7. Compares current variants against a **persistent state file** (`.seen_variants.json`) that tracks every `product:color:size:discount%` combination seen so far. Deals with at least one previously unseen combination are flagged as "new" — this covers new products, new sizes/colours, **and** price changes. The state survives server restarts.
8. Sends notifications for new deals via enabled channels. Preview modes (CLI/HTML) run alongside real notifications when active.

## Quick Start

### Prerequisites

- Python 3.11+

### Installation

```bash
git clone https://github.com/kequach/uniqlo-sales-alerter.git
cd uniqlo-sales-alerter
python -m pip install -e ".[dev]"
```

### Preview mode (recommended first step)

Run a single check and see matching deals — no notifications are sent:

```bash
python -m uniqlo_sales_alerter --preview-cli   # text output in terminal
python -m uniqlo_sales_alerter --preview-html   # visual HTML report with images
```

This is the best way to verify your filters are working before enabling Telegram/email.

### Run the server

```bash
python -m uniqlo_sales_alerter
```

Or directly with uvicorn for development:

```bash
python -m uvicorn uniqlo_sales_alerter.main:app --reload
```

The server starts on `http://localhost:8000`. On startup it runs an initial sale check, then repeats every 30 minutes (configurable).

Open `http://localhost:8000/docs` for the interactive API documentation.

## Configuration

Edit `config.yaml` in the project root. All settings have sensible defaults.

```yaml
uniqlo:
  # Country/language path for the Uniqlo store.
  # Examples: "de/de" (Germany), "uk/en" (UK), "fr/fr" (France)
  country: "de/de"

  # How often to check for sales (in minutes)
  check_interval_minutes: 30

filters:
  # Which genders to include: men, women, unisex, kids, baby
  gender:
    - men
    - women

  # Minimum discount percentage to surface a deal (default: 50)
  min_sale_percentage: 50

  # Only show items available in at least one of these sizes.
  # Stock is verified per colour×size variant in real-time; out-of-stock
  # sizes are excluded and URLs point to an in-stock colour.
  # Omit or leave a category empty to skip filtering for it.
  sizes:
    clothing:       # XXS, XS, S, M, L, XL, XXL, 3XL
      - S
      - M
      - L
    pants:          # 22inch – 40inch (women from 22, men from 28)
      - "32inch"
    shoes:          # 37, 37.5, 38, 38.5, 39, 40, 41, 41.5, 42, 42.5, 43
      - "42"
      - "42.5"
    one_size: false # bags, hats, accessories, etc.

  # Full Uniqlo product URLs to always include when in stock — even if the
  # item is not on sale.  The colour and size from each URL are preferred
  # during stock verification, and the watched size is included even when
  # it falls outside your size filter.
  watched_urls:
    - "https://www.uniqlo.com/de/de/products/E483045-000/00?colorDisplayCode=70&sizeDisplayCode=003"

notifications:
  # Preview modes — generate local previews alongside real notifications.
  # Also available via CLI: --preview-cli / --preview-html
  preview_cli: false   # print deals to the terminal (text)
  preview_html: false  # generate an HTML report with images, open in browser

  # Notification mode (see "Notification modes" section below)
  notify_on: all_then_new   # "all_then_new", "new_deals", or "every_check"

  channels:
    telegram:
      enabled: true
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"

    email:
      enabled: true
      smtp_host: "smtp.gmail.com"
      smtp_port: 587
      use_tls: true
      smtp_user: "${SMTP_USER}"
      smtp_password: "${SMTP_PASSWORD}"
      from_address: "alerts@example.com"
      to_addresses:
        - "you@example.com"
```

### Environment variables

Sensitive values use `${ENV_VAR}` placeholders in `config.yaml` that are resolved from environment variables at startup, so you never need to put secrets in the YAML file.

| Variable | Used by | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Telegram | Chat / group / channel ID to send messages to |
| `SMTP_USER` | Email | SMTP login username (often your email address) |
| `SMTP_PASSWORD` | Email | SMTP password or app-specific password |

Set them in your shell before starting the server:

```bash
# Telegram
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
export TELEGRAM_CHAT_ID="987654321"

# Email (SMTP)
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="abcd efgh ijkl mnop"   # Gmail App Password (16 chars, no spaces needed)
```

On Windows (PowerShell):

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
$env:TELEGRAM_CHAT_ID   = "987654321"
$env:SMTP_USER           = "you@gmail.com"
$env:SMTP_PASSWORD       = "abcd efgh ijkl mnop"
```

You can also put them in a `.env` file (already git-ignored) and source it before running.

### Size filter reference

All values are strings and must match **exactly** as the API returns them (case-insensitive matching is applied internally).

| Category    | Config key  | Valid values                                                                      |
|-------------|-------------|-----------------------------------------------------------------------------------|
| Clothing    | `clothing`  | `XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`                                  |
| Pants       | `pants`     | `22inch` – `40inch` (women's jeans start at 22, men's at 28)                     |
| Shoes       | `shoes`     | `37`, `37.5`, `38`, `38.5`, `39`, `40`, `41`, `41.5`, `42`, `42.5`, `43`        |
| One Size    | `one_size`  | Boolean (`true`/`false`) — matches bags, hats, accessories labelled "One Size"   |

A product passes the size filter if it has **at least one** in-stock size matching any of your configured values across all categories. Omitting or leaving a category empty means it won't contribute to filtering (but other categories still apply). If **all** size categories are empty/omitted, every product passes regardless of size.

### Supported countries

The `country` field maps to a Uniqlo regional store. Known working values:

| Country   | Value   |
|-----------|---------|
| Germany   | `de/de` |
| UK        | `uk/en` |
| France    | `fr/fr` |
| Spain     | `es/es` |
| Italy     | `it/it` |

## Preview Modes

Preview modes let you see what deals match your filters locally. When enabled via config, they run **alongside** real notification channels (Telegram, Email), so you can preview and send at the same time. When used via CLI flags, they run a one-shot check without starting the web server.

| Mode | CLI flag | What it does |
|------|----------|--------------|
| **CLI** | `--preview-cli` | Prints deals to the terminal (colour-coded) |
| **HTML** | `--preview-html` | Generates an HTML report with product images and opens it in your browser |

**Via CLI flags** (one-shot, then exit):

```bash
python -m uniqlo_sales_alerter --preview-cli
python -m uniqlo_sales_alerter --preview-html
python -m uniqlo_sales_alerter --preview-html --config path/to/config.yaml
```

**Via config** (server keeps running, preview runs alongside real channels):

```yaml
notifications:
  preview_cli: true    # terminal output
  # or
  preview_html: true   # HTML report in browser
```

Both can be enabled simultaneously.

### CLI preview example

`--preview-cli` prints a compact, colour-coded summary to the terminal. Each deal shows the name, price drop, discount percentage, and a direct link per available size:

```
============================================================
  Uniqlo Sale Alert — 3 deal(s)
============================================================

  1. AIRism Baumwolle T-Shirt (oversized, Rundhals)
     €19.90 -> €3.90  (-80%)
        XS  https://www.uniqlo.com/de/de/products/E465185-000/00?colorDisplayCode=64&sizeDisplayCode=002
         S  https://www.uniqlo.com/de/de/products/E465185-000/00?colorDisplayCode=64&sizeDisplayCode=003

  2. Ultra Light Down Jacke [WATCHED]
     €79.90 -> €29.90  (-63%)
         M  https://www.uniqlo.com/de/de/products/E482873-000/00?colorDisplayCode=09&sizeDisplayCode=004
         L  https://www.uniqlo.com/de/de/products/E482873-000/00?colorDisplayCode=09&sizeDisplayCode=005

  3. Souffle Yarn Pullover
     €39.90 -> €19.90  (-50%)
         M  https://www.uniqlo.com/de/de/products/E476543-000/00?colorDisplayCode=01&sizeDisplayCode=004

  Scanned 284 sale items, 3 matched your filters.
```

Each size links directly to a colour+size variant that is verified as in-stock. Watched items are tagged with `[WATCHED]`.

### HTML preview example

`--preview-html` generates a self-contained HTML file styled in Uniqlo's corporate identity and opens it in your default browser:

```
  HTML report saved to: C:\Repo\uniqlo-sales-alerter\reports\uniqlo_deals_20260408_123000.html
  Scanned 284 sale items, 47 matched your filters.
```

![HTML preview report](docs/img/html_preview.png)

The report includes product images from Uniqlo's CDN, strikethrough original prices with red sale prices and green discount badges, and clickable size chips that link directly to in-stock variants on uniqlo.com. Dark mode is supported via `prefers-color-scheme`. Reports are saved to `reports/` by default (git-ignored).

## Notification Modes

The `notify_on` setting in `config.yaml` controls which deals are included in each notification:

| Mode | Config value | Behaviour |
|------|-------------|-----------|
| **All then new** *(default)* | `notify_on: all_then_new` | Sends **all** matching deals on the **first check after startup**, then only deals with at least one change on subsequent checks (see [What triggers a new notification](#what-triggers-a-new-notification) below). On every restart the initial "full" notification is sent again. |
| **New deals only** | `notify_on: new_deals` | Only deals with at least one change since the last check. The state file is loaded on startup, so restarts **do not** re-trigger already-seen deals. |
| **All matching deals** | `notify_on: every_check` | **Every** matching deal is sent on every check. Useful for daily digests or full overviews. |

```yaml
notifications:
  notify_on: all_then_new    # or "new_deals" or "every_check"
```

### How "new deals" tracking works

The system maintains a **local state file** (`.seen_variants.json` in the project root) that stores every `product_id:colorDisplayCode:sizeDisplayCode:discount%` combination seen in the previous check. On each run:

1. After filtering and stock verification, variant keys are extracted from each deal's URLs together with the current discount percentage.
2. A deal is "new" if it has **at least one variant** not present in the stored set — this means a product that gains a new available size or colour, **or whose discount percentage changes**, is re-flagged as new.
3. The state file is updated with the current set of variants.

In `all_then_new` mode (the default), the saved state is **not loaded on startup** — the set starts empty, so the first check treats everything as new. After that first check the state is saved normally and subsequent checks only flag genuinely new variants. On restart, the cycle repeats.

In `new_deals` mode, the saved state **is loaded on startup**, so previously seen variants stay suppressed across restarts. To reset the tracking (e.g. to re-trigger all notifications), delete `.seen_variants.json`.

The state file is created automatically and is git-ignored by default.

The mode applies to all notification channels (Telegram, Email) and to preview-via-config. CLI previews (`--preview-cli` / `--preview-html`) always show all matching deals since there is no previous check to diff against.

### What triggers a new notification

In `all_then_new` and `new_deals` modes, a deal is included in the notification when **any** of the following changes since the last check:

| Change | Example | Triggers notification? |
|--------|---------|:----------------------:|
| **New product appears** | A product you've never seen before goes on sale | Yes |
| **New size becomes available** | A product gains size L that was previously out of stock | Yes |
| **New colour becomes available** | A new colour variant comes into stock | Yes |
| **Discount percentage changes** | A product goes from 50% off to 60% off | Yes |
| **Product goes back on sale** | A product that left the sale list re-appears | Yes |
| No change (same sizes, colours, and price) | Product is still on sale at the same discount | No |

This applies equally to **regular sale items** and **watched items**. A watched product that stays in stock at the same price with the same sizes will not re-trigger a notification — only a meaningful change (new size, new colour, or a price change) will.

## Notifications

### Telegram

1. Create a bot via [@BotFather](https://t.me/BotFather) and save the token.
2. Get your chat ID (send a message to your bot, then check `https://api.telegram.org/bot<token>/getUpdates`).
3. Set the environment variables and enable the channel in `config.yaml`.

Each deal is sent as a photo message with the product image and a caption showing the price drop, discount percentage, available sizes, and a link to the product page.

### Email

Deals are sent as a single HTML email with product images, prices, discount badges, and direct links per size.

**Setup:**

1. Enable the email channel in `config.yaml`:

```yaml
notifications:
  channels:
    email:
      enabled: true
      smtp_host: "smtp.gmail.com"     # your SMTP server
      smtp_port: 587
      use_tls: true
      smtp_user: "${SMTP_USER}"       # resolved from env var
      smtp_password: "${SMTP_PASSWORD}"
      from_address: "alerts@example.com"
      to_addresses:
        - "you@example.com"
        - "friend@example.com"        # multiple recipients supported
```

2. Set the environment variables (see [Environment variables](#environment-variables) above).

**Provider-specific notes:**

| Provider | `smtp_host` | `smtp_port` | Notes |
|----------|-------------|-------------|-------|
| Gmail | `smtp.gmail.com` | `587` | Requires an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password). Enable 2FA first, then generate one under *Security > App passwords*. |
| Outlook / Microsoft 365 | `smtp.office365.com` | `587` | Use your full email as `smtp_user`. |
| Yahoo | `smtp.mail.yahoo.com` | `587` | Requires an [App Password](https://help.yahoo.com/kb/generate-manage-third-party-passwords-sln15241.html). |
| Custom / self-hosted | Your server | `587` or `465` | Set `use_tls: true` for STARTTLS (port 587) or implicit TLS (port 465). |

### Adding a custom channel

The notification system uses Python's `Protocol` for structural subtyping. To add a new channel:

1. Create a new file in `src/uniqlo_sales_alerter/notifications/` (e.g. `discord.py`).
2. Implement the `Notifier` protocol:

```python
from uniqlo_sales_alerter.models.products import SaleItem

class DiscordNotifier:
    def __init__(self, config):
        self._config = config

    def is_enabled(self) -> bool:
        return self._config.enabled

    async def send(self, deals: list[SaleItem]) -> None:
        # Send deals to Discord
        ...
```

3. Register it in the dispatcher (in `notifications/dispatcher.py`) or at runtime via `dispatcher.register(notifier)`.

## Deployment on Linux (Raspberry Pi / VPS)

You can run the alerter as a systemd service so it starts automatically on boot, restarts on failure, and keeps running in the background.

### 1. Install the project

```bash
cd /opt
sudo git clone https://github.com/kequach/uniqlo-sales-alerter.git
sudo chown -R $(whoami):$(whoami) uniqlo-sales-alerter
cd uniqlo-sales-alerter

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp config.yaml config.yaml.bak   # optional backup
nano config.yaml                  # edit filters, notifications, etc.
```

### 3. Create an environment file for secrets

```bash
sudo nano /etc/uniqlo-sales-alerter.env
```

```ini
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
```

Lock it down so only root can read it:

```bash
sudo chmod 600 /etc/uniqlo-sales-alerter.env
```

### 4. Create a systemd service

```bash
sudo nano /etc/systemd/system/uniqlo-alerter.service
```

```ini
[Unit]
Description=Uniqlo Sales Alerter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/uniqlo-sales-alerter
EnvironmentFile=/etc/uniqlo-sales-alerter.env
ExecStart=/opt/uniqlo-sales-alerter/.venv/bin/python -m uniqlo_sales_alerter
Restart=on-failure
RestartSec=30

# Hardening (optional but recommended)
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/uniqlo-sales-alerter
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

> **Note:** Change `User=pi` to whatever user you want the service to run as. On a VPS this might be `ubuntu`, `deploy`, etc.

### 5. Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable uniqlo-alerter   # start on boot
sudo systemctl start uniqlo-alerter    # start now
```

### 6. Manage the service

```bash
sudo systemctl status uniqlo-alerter   # check if running
sudo journalctl -u uniqlo-alerter -f   # live log output
sudo systemctl restart uniqlo-alerter  # restart after config changes
sudo systemctl stop uniqlo-alerter     # stop
```

### 7. Update to the latest version

```bash
cd /opt/uniqlo-sales-alerter
source .venv/bin/activate
git pull
pip install -e .                         # only needed if dependencies changed
sudo systemctl restart uniqlo-alerter
```

The editable install loads code directly from the source tree, so `git pull` brings in all code changes. Re-running `pip install -e .` is only necessary when `pyproject.toml` has new or updated dependencies. The service restart is always required to pick up the changes.

### Quick test before enabling

Before setting up the service, verify everything works:

```bash
cd /opt/uniqlo-sales-alerter
source .venv/bin/activate
export $(cat /etc/uniqlo-sales-alerter.env | xargs)
python -m uniqlo_sales_alerter --preview-cli
```

If you see matching deals in the terminal, the config, API access, and (optionally) notifications are all working.

## Development

### Run tests

```bash
python -m pytest tests/ -v
```

### Lint

```bash
python -m ruff check src/ tests/
```

### Project structure

```
src/uniqlo_sales_alerter/
├── __main__.py          # CLI entry-point (--preview, server)
├── main.py              # FastAPI app, lifespan, scheduler
├── config.py            # YAML + env var config loading
├── api/routes.py        # REST endpoints
├── clients/uniqlo.py    # Uniqlo Commerce API client
├── models/products.py   # Pydantic models
├── services/sale_checker.py  # Filtering and caching
└── notifications/
    ├── base.py          # Notifier protocol
    ├── console.py       # CLI preview (terminal output)
    ├── html_report.py   # HTML preview (browser report with images)
    ├── telegram.py      # Telegram channel
    ├── email.py         # Email channel
    └── dispatcher.py    # Multi-channel dispatcher
```

## License

[MIT](LICENSE)
