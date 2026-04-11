# Uniqlo Sales Alerter

A Python web server that monitors [Uniqlo](https://www.uniqlo.com) sales and notifies you when items match your criteria. It talks directly to Uniqlo's internal Commerce API — no browser automation or scraping required.

## Features

- **Periodic sale monitoring** — polls the Uniqlo catalogue on a configurable interval
- **Configurable filters** — gender, minimum discount %, clothing/pants/shoe sizes (verified against real-time stock per variant), watched product URLs (notified whenever in stock, even without a sale)
- **Preview modes** — CLI (terminal text) or HTML (visual report with product images in the browser)
- **Pluggable notifications** — Telegram (with product images), Email (HTML), extensible to Discord/Slack/etc.
- **REST API** — query current deals, trigger manual checks, view configuration (interactive docs at `/docs`)

## Getting Started

This section walks you through the full setup — from installation to receiving your first email alert.

### Prerequisites

- **Python 3.11 or newer** — [download here](https://www.python.org/downloads/) if you don't have it. Check with `python --version` (or `python3 --version` on Linux/macOS)
- **A Gmail account** (for email alerts) or a Telegram account (for Telegram alerts) — or both

### 1. Download and install

**Option A — with Git:**

```bash
git clone https://github.com/kequach/uniqlo-sales-alerter.git
cd uniqlo-sales-alerter
python -m pip install -e .
```

**Option B — without Git (zip download):**

1. Go to [github.com/kequach/uniqlo-sales-alerter](https://github.com/kequach/uniqlo-sales-alerter).
2. Click the green **Code** button, then **Download ZIP**.
3. Extract the zip file and open a terminal in the extracted folder.
4. Run:

```bash
python -m pip install -e .
```

> On Linux/macOS you may need to use `python3` instead of `python`.

### 2. Choose your country

Open `config.yaml` in a text editor and set the Uniqlo store you want to monitor:

```yaml
uniqlo:
  country: "de/de"              # see table below
  check_interval_minutes: 30    # how often to check (in minutes)
```

| Country | Value |
|---------|-------|
| **Europe** | |
| Germany | `de/de` |
| UK | `uk/en` |
| France | `fr/fr` |
| Spain | `es/es` |
| Italy | `it/it` |
| Belgium (FR) | `be/fr` |
| Belgium (NL) | `be/nl` |
| Netherlands | `nl/nl` |
| Denmark | `dk/en` |
| Sweden | `se/en` |
| **Americas** | |
| US | `us/en` |
| Canada (EN) | `ca/en` |
| Canada (FR) | `ca/fr` |
| **Asia-Pacific** | |
| Japan | `jp/ja` |
| South Korea | `kr/ko` |
| Australia | `au/en` |
| India | `in/en` |
| Singapore | `sg/en` |
| Malaysia | `my/en` |
| Indonesia | `id/en` |
| Vietnam | `vn/vi` |

### 3. Configure your filters

In the same `config.yaml`, tell the alerter what you're looking for:

```yaml
filters:
  gender:
    - men          # options: men, women, unisex, kids, baby
    - women

  min_sale_percentage: 50   # only show items at least 50% off

  sizes:
    clothing:      # your clothing sizes (XXS, XS, S, M, L, XL, XXL, 3XL)
      - S
      - M
      - L
    pants:         # your pants sizes (22inch – 40inch)
      - "32inch"
    shoes:         # your shoe sizes (37 – 43, half sizes supported)
      - "42"
      - "42.5"
    one_size: false  # set to true to include bags, hats, accessories
```

Only sizes that are actually **in stock** will be shown — out-of-stock sizes are automatically excluded. You can leave any size category empty or remove it entirely if you don't need it.

**Watching specific products** (optional) — if there's a specific product you want to track regardless of whether it's on sale, add its full URL to `watched_urls`:

```yaml
filters:
  watched_urls:
    - "https://www.uniqlo.com/de/de/products/E483045-000/00?colorDisplayCode=70&sizeDisplayCode=003"
```

You'll be notified whenever the watched item is in stock, even if it's not discounted.

<details>
<summary><strong>Size filter reference</strong> — all valid values per category</summary>

| Category    | Config key  | Valid values                                                                      |
|-------------|-------------|-----------------------------------------------------------------------------------|
| Clothing    | `clothing`  | `XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL`                                  |
| Pants       | `pants`     | `22inch` – `40inch` (women's jeans start at 22, men's at 28)                     |
| Shoes       | `shoes`     | `37`, `37.5`, `38`, `38.5`, `39`, `40`, `41`, `41.5`, `42`, `42.5`, `43`        |
| One Size    | `one_size`  | Boolean (`true`/`false`) — matches bags, hats, accessories labelled "One Size"   |

A product passes the size filter if it has **at least one** in-stock size matching any of your configured values across all categories. If **all** size categories are empty/omitted, every product passes regardless of size.

</details>

### 4. Set up email notifications (Gmail)

This is the easiest way to get alerts. You'll need a Gmail account and an **App Password** (not your regular Gmail password).

**Step 1 — Generate a Gmail App Password:**

1. Go to [myaccount.google.com](https://myaccount.google.com) and sign in.
2. Navigate to **Security** and make sure **2-Step Verification** is turned on (required for App Passwords).
3. Go to [App Passwords](https://myaccount.google.com/apppasswords) (or search "App Passwords" in your Google Account settings).
4. Select **Mail** as the app, give it a name like "Uniqlo Alerter", and click **Generate**.
5. Copy the 16-character password that appears (e.g. `abcd efgh ijkl mnop`).

**Step 2 — Configure the email channel in `config.yaml`:**

```yaml
notifications:
  channels:
    email:
      enabled: true
      smtp_host: "smtp.gmail.com"
      smtp_port: 587
      use_tls: true
      smtp_user: "${SMTP_USER}"
      smtp_password: "${SMTP_PASSWORD}"
      from_address: "you@gmail.com"        # your Gmail address
      to_addresses:
        - "you@gmail.com"                  # where to receive alerts
        - "friend@example.com"             # add more recipients if you want
```

**Step 3 — Set the environment variables** so your password stays out of the config file:

Linux / macOS:

```bash
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="abcd efgh ijkl mnop"
```

Windows (PowerShell):

```powershell
$env:SMTP_USER     = "you@gmail.com"
$env:SMTP_PASSWORD = "abcd efgh ijkl mnop"
```

> You can also put them in a `.env` file (already git-ignored) and source it before running.

### 5. Set up Telegram notifications (optional)

If you'd also like alerts on Telegram:

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, follow the prompts, and copy the **bot token** it gives you.
3. Send any message to your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser to find your **chat ID** (look for `"chat":{"id":123456789}`).
4. Enable the channel in `config.yaml`:

```yaml
notifications:
  channels:
    telegram:
      enabled: true
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"
```

5. Set the environment variables:

Linux / macOS:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
export TELEGRAM_CHAT_ID="987654321"
```

Windows (PowerShell):

```powershell
$env:TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
$env:TELEGRAM_CHAT_ID   = "987654321"
```

### 6. Test your setup

Before running the server, do a quick preview to make sure your filters and notifications are configured correctly:

```bash
python -m uniqlo_sales_alerter --preview-cli
```

This runs a single check and prints matching deals to the terminal — no notifications are sent. If you see deals listed, your configuration is working.

You can also generate a visual HTML report:

```bash
python -m uniqlo_sales_alerter --preview-html
```

### 7. Start the server

```bash
python -m uniqlo_sales_alerter
```

The server starts on `http://localhost:8000`. On startup it runs an initial sale check, then repeats every 30 minutes (configurable via `check_interval_minutes` in `config.yaml`). You'll receive notifications through the channels you enabled whenever new deals are found.

Open `http://localhost:8000/docs` for the interactive API documentation.

## Notifications

### Telegram

Each deal is sent as a photo message with the product image and a caption showing the price drop, discount percentage, available sizes, and a link to the product page.

### Email

Deals are sent as a single HTML email with product images, prices, discount badges, and direct links per size.

**Provider-specific notes:**

| Provider | `smtp_host` | `smtp_port` | Notes |
|----------|-------------|-------------|-------|
| Gmail | `smtp.gmail.com` | `587` | Requires an [App Password](https://support.google.com/accounts/answer/185833) (not your regular password). Enable 2FA first, then generate one under *Security > App passwords*. |
| Outlook / Microsoft 365 | `smtp.office365.com` | `587` | Use your full email as `smtp_user`. |
| Yahoo | `smtp.mail.yahoo.com` | `587` | Requires an [App Password](https://help.yahoo.com/kb/generate-manage-third-party-passwords-sln15241.html). |
| Custom / self-hosted | Your server | `587` or `465` | Set `use_tls: true` for STARTTLS (port 587) or implicit TLS (port 465). |

### Notification modes

The `notify_on` setting in `config.yaml` controls which deals are included in each notification:

| Mode | Config value | Behaviour |
|------|-------------|-----------|
| **All then new** *(default)* | `notify_on: all_then_new` | Sends **all** matching deals on the **first check after startup**, then only deals with at least one change on subsequent checks. On every restart the initial "full" notification is sent again. |
| **New deals only** | `notify_on: new_deals` | Only deals with at least one change since the last check. The state file is loaded on startup, so restarts **do not** re-trigger already-seen deals. |
| **All matching deals** | `notify_on: every_check` | **Every** matching deal is sent on every check. Useful for daily digests or full overviews. |

```yaml
notifications:
  notify_on: all_then_new    # or "new_deals" or "every_check"
```

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

### How tracking works

The system maintains a **local state file** (`.seen_variants.json` in the project root) that stores every `product_id:colorDisplayCode:sizeDisplayCode:discount%` combination seen in the previous check. On each run:

1. After filtering and stock verification, variant keys are extracted from each deal's URLs together with the current discount percentage.
2. A deal is "new" if it has **at least one variant** not present in the stored set — this means a product that gains a new available size or colour, **or whose discount percentage changes**, is re-flagged as new.
3. The state file is updated with the current set of variants.

In `all_then_new` mode (the default), the saved state is **not loaded on startup** — the set starts empty, so the first check treats everything as new. After that first check the state is saved normally and subsequent checks only flag genuinely new variants. On restart, the cycle repeats.

In `new_deals` mode, the saved state **is loaded on startup**, so previously seen variants stay suppressed across restarts. To reset the tracking (e.g. to re-trigger all notifications), delete `.seen_variants.json`.

The state file is created automatically and is git-ignored by default.

The mode applies to all notification channels (Telegram, Email) and to preview-via-config. CLI previews (`--preview-cli` / `--preview-html`) always show all matching deals since there is no previous check to diff against.

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

## How It Works

The server reverse-engineers Uniqlo's internal Commerce API (the same one their website's SPA uses). On each check it:

1. Fetches only sale items via `flagCodes=discount` with pagination (100 items per page), avoiding the full catalogue.
2. Verifies each item has a promo price lower than the base price.
3. Computes the discount percentage and applies your configured filters (gender, sizes, min discount %).
4. **Verifies real-time stock per variant** — for each matching product, fetches the stock endpoint to check which colour×size combinations are actually purchasable online. Sizes that are out of stock are excluded. Products where all matching sizes are sold out are dropped entirely.
5. Generates **direct variant URLs** pointing to an **in-stock colour** for each matching size (e.g. `…/E479257-000/00?colorDisplayCode=07&sizeDisplayCode=004`). The colour with the highest stock quantity is preferred, so links lead to purchasable variants.
6. Caches the results for fast API responses.
7. Compares current variants against a **persistent state file** (`.seen_variants.json`) that tracks every `product:color:size:discount%` combination seen so far. Deals with at least one previously unseen combination are flagged as "new" — this covers new products, new sizes/colours, **and** price changes. The state survives server restarts.
8. Sends notifications for new deals via enabled channels. Preview modes (CLI/HTML) run alongside real notifications when active.

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
