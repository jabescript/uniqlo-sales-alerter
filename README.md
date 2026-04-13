# Uniqlo Sales Alerter

A self-hosted server that monitors [Uniqlo](https://www.uniqlo.com) sales and sends you notifications when items match your criteria. Talks directly to Uniqlo's internal Commerce API — no browser automation or scraping required.

![Mail report](docs/img/mail.png)

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Preview Modes](#preview-modes)
- [Development](#development)

## Quick Start

The fastest way to get running is with Docker. You can configure via a YAML file or purely through environment variables.

### Docker with config file

Create a **config.yaml** — copy the [example config](config.yaml) and set your country + filters:

```yaml
uniqlo:
  country: "de/de"              # see supported countries below
  check_interval_minutes: 30

filters:
  gender: [men, women]
  min_sale_percentage: 30
  sizes:
    clothing: [S, M, L]
```

Create an **.env** file for notification secrets (only include what you use):

```env
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=987654321
```

Then start with Docker Compose (using the shipped [`docker-compose.yml`](docker-compose.yml)):

```bash
docker compose up -d
```

Or with `docker run`:

```bash
docker run -d \
  --name uniqlo-alerter \
  -p 8000:8000 \
  -v ./config.yaml:/app/config.yaml:ro \
  -v alerter-state:/app/data \
  -e STATE_FILE=/app/data/.seen_variants.json \
  --env-file .env \
  --restart unless-stopped \
  kequach/uniqlo-sales-alerter
```

### Docker with env vars only

You can skip the config file entirely and pass everything as `-e` flags. Only values that differ from the defaults need to be set. This example uses Gmail notifications for Germany with a 30% minimum discount:

```bash
docker run -d \
  --name uniqlo-alerter \
  -p 8000:8000 \
  -v alerter-state:/app/data \
  -e STATE_FILE=/app/data/.seen_variants.json \
  -e UNIQLO_COUNTRY=de/de \
  -e UNIQLO_CHECK_INTERVAL=30 \
  -e FILTER_GENDER=men,women \
  -e FILTER_MIN_SALE_PERCENTAGE=30 \
  -e FILTER_SIZES_CLOTHING=S,M,L \
  -e EMAIL_ENABLED=true \
  -e SMTP_USER=you@gmail.com \
  -e SMTP_PASSWORD=your-app-password \
  -e SMTP_FROM=you@gmail.com \
  -e SMTP_TO=you@gmail.com \
  --restart unless-stopped \
  kequach/uniqlo-sales-alerter
```

> When both a config file and env vars are present, env vars take precedence. See the full [env var reference](#environment-variables).

### Without Docker

Requires [Python 3.11+](https://www.python.org/downloads/). On Linux/macOS you may need `python3` instead of `python`.

**1. Install:**

```bash
git clone https://github.com/kequach/uniqlo-sales-alerter.git
cd uniqlo-sales-alerter
python -m pip install -e .
```

Or [download the ZIP](https://github.com/kequach/uniqlo-sales-alerter/archive/refs/heads/main.zip), extract, and run `pip install -e .` in the folder.

**2. Configure:** edit `config.yaml` — set your country, filters, and at least one notification channel (see [Configuration](#configuration)).

**3. Try it out** with a one-off HTML preview (opens in your browser, no notification setup needed):

```bash
python -m uniqlo_sales_alerter --preview-html
```

**4. Or start the server** to run on a schedule and send notifications:

```bash
export SMTP_USER="you@gmail.com"            # Linux / macOS
export SMTP_PASSWORD="your-app-password"
python -m uniqlo_sales_alerter
```

```powershell
$env:SMTP_USER     = "you@gmail.com"        # Windows (PowerShell)
$env:SMTP_PASSWORD = "your-app-password"
python -m uniqlo_sales_alerter
```

The server runs on `http://localhost:8000` with interactive API docs at `/docs`.

## Configuration

Configuration can be provided via `config.yaml`, [environment variables](#environment-variables), or both (env vars take precedence). Secrets can be referenced in YAML with `${VAR_NAME}` syntax so they stay out of version control.

### Supported countries

**Full support** — discount percentage, original vs. sale price, all filters:

| Country | Value | | Country | Value |
|---------|-------|-|---------|-------|
| Germany | `de/de` | | Australia | `au/en` |
| UK | `uk/en` | | India | `in/en` |
| France | `fr/fr` | | Indonesia | `id/en` |
| Spain | `es/es` | | Vietnam | `vn/vi` |
| Italy | `it/it` | | Philippines | `ph/en` |
| Belgium (FR) | `be/fr` | | Malaysia | `my/en` |
| Belgium (NL) | `be/nl` | | Thailand | `th/en` |
| Netherlands | `nl/nl` | | | |
| Denmark | `dk/en` | | | |
| Sweden | `se/en` | | | |

**Limited support** — sale-flagged items only (no discount percentage):

| Country | Value |
|---------|-------|
| United States | `us/en` |
| Canada | `ca/en` |
| Japan | `jp/ja` |
| South Korea | `kr/ko` |
| Singapore | `sg/en` |

> **What does "limited support" mean?** These stores flag items as on sale, but their API does not expose the original (pre-sale) price — only the current price. This means the alerter cannot calculate how much an item is discounted, so notifications will show the current price with a "Sale" label instead of a percentage. The `min_sale_percentage` filter is automatically skipped for these countries; gender and size filters still work normally.

**Singapore requires `sale_paths`** — Singapore organises most of its sale catalogue into category paths rather than flagging items individually. Without `sale_paths` configured, the alerter will only find a handful of items. See [Sale category paths](#sale-category-paths).

### Filters

```yaml
filters:
  gender:
    - men          # options: men, women, unisex, kids, baby
    - women

  min_sale_percentage: 50   # only show items at least 50% off (ignored for limited countries)

  sizes:
    clothing:      # XXS, XS, S, M, L, XL, XXL, 3XL
      - S
      - M
      - L
    pants:         # 22inch – 40inch
      - "32inch"
    shoes:         # 37 – 43, half sizes supported
      - "42"
      - "42.5"
    one_size: false  # set to true to include bags, hats, accessories
```

Only sizes that are actually **in stock** will be shown. You can leave any size category empty or remove it entirely.

<details>
<summary><strong>Size filter reference</strong></summary>

| Category | Config key | Valid values |
|----------|-----------|-------------|
| Clothing | `clothing` | `XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `3XL` |
| Pants | `pants` | `22inch` – `40inch` (women's jeans start at 22, men's at 28) |
| Shoes | `shoes` | `37`, `37.5`, `38`, `38.5`, `39`, `40`, `41`, `41.5`, `42`, `42.5`, `43` |
| One Size | `one_size` | Boolean — matches bags, hats, accessories labelled "One Size" |

A product passes if it has **at least one** in-stock size matching any configured value. If all categories are empty, every product passes.

</details>

### Watched products

Track a specific product regardless of whether it's on sale:

```yaml
filters:
  watched_urls:
    - "https://www.uniqlo.com/de/de/products/E483045-000/00?colorDisplayCode=70&sizeDisplayCode=003"
```

You'll be notified whenever the item is in stock, even without a discount.

### Sale category paths

Some countries (notably Singapore) organise their sale items into category paths instead of flagging them. Without configuring `sale_paths`, the alerter will miss most sale items for these countries.

To find the path IDs for your country, open the Uniqlo sale page and look at the URL:

```
https://www.uniqlo.com/sg/en/feature/sale/men?path=5856&flagCodes=discount
                                                    ^^^^
```

Add the path IDs to your config:

```yaml
uniqlo:
  country: "sg/en"
  sale_paths: ["5855", "5856", "5857", "5858"]
```

<details>
<summary><strong>Known Singapore paths (as of 2026)</strong></summary>

| Path | Category |
|------|----------|
| `5855` | All sale |
| `5856` | Men |
| `5857` | Women |
| `5858` | Kids |

</details>

### Notifications

#### Email (Gmail)

Deals are sent as a single HTML email with product images, prices, discount badges, and direct links per size.

1. Go to [myaccount.google.com](https://myaccount.google.com) > **Security** > enable **2-Step Verification**.
2. Go to [App Passwords](https://myaccount.google.com/apppasswords), create one for "Mail", and copy the 16-character password.
3. Add to `config.yaml` (or use the equivalent [env vars](#environment-variables)):

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
      from_address: "you@gmail.com"
      to_addresses:
        - "you@gmail.com"
```

<details>
<summary><strong>Other email providers</strong></summary>

| Provider | `smtp_host` | `smtp_port` | Notes |
|----------|-------------|-------------|-------|
| Gmail | `smtp.gmail.com` | `587` | Requires [App Password](https://support.google.com/accounts/answer/185833). Enable 2FA first. |
| Outlook / Microsoft 365 | `smtp.office365.com` | `587` | Use your full email as `smtp_user`. |
| Yahoo | `smtp.mail.yahoo.com` | `587` | Requires [App Password](https://help.yahoo.com/kb/generate-manage-third-party-passwords-sln15241.html). |
| Custom / self-hosted | Your server | `587` or `465` | Set `use_tls: true` for STARTTLS (587) or implicit TLS (465). |

</details>

#### Telegram

Each deal is sent as a photo message with the product image, price drop, discount percentage, available sizes, and a link to the product page.

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, and copy the **bot token**.
2. Send any message to your new bot, then open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` to find your **chat ID**.
3. Add to `config.yaml` (or use the equivalent [env vars](#environment-variables)):

```yaml
notifications:
  channels:
    telegram:
      enabled: true
      bot_token: "${TELEGRAM_BOT_TOKEN}"
      chat_id: "${TELEGRAM_CHAT_ID}"
```

#### Notification modes

The `notify_on` setting controls which deals trigger a notification:

| Mode | Config value | Behaviour |
|------|-------------|-----------|
| **All then new** *(default)* | `all_then_new` | All deals on first check after startup, then only changes. |
| **New deals only** | `new_deals` | Only changes, even across restarts (state persists). |
| **Every check** | `every_check` | All matching deals on every check. Good for digests. |

<details>
<summary><strong>What counts as a "change"?</strong></summary>

| Change | Triggers notification? |
|--------|:----------------------:|
| New product appears on sale | Yes |
| New size becomes available | Yes |
| New colour becomes available | Yes |
| Discount percentage changes | Yes |
| Product goes back on sale | Yes |
| No change (same sizes, colours, price) | No |

The system tracks every `product:color:size:discount%` combination. A deal is "new" if it has at least one previously unseen combination. In `all_then_new` mode the state resets on restart; in `new_deals` mode it persists to `.seen_variants.json`. Delete that file to reset tracking.

</details>

### Environment variables

Every config option can be set via environment variables instead of (or in addition to) `config.yaml`. When both are present, **env vars win**.

<details>
<summary><strong>Full env var reference</strong></summary>

| Env variable | Type | Config equivalent |
|---|---|---|
| `UNIQLO_COUNTRY` | string | `uniqlo.country` |
| `UNIQLO_CHECK_INTERVAL` | int | `uniqlo.check_interval_minutes` |
| `UNIQLO_SALE_PATHS` | comma-separated | `uniqlo.sale_paths` |
| `FILTER_GENDER` | comma-separated | `filters.gender` |
| `FILTER_MIN_SALE_PERCENTAGE` | float | `filters.min_sale_percentage` |
| `FILTER_SIZES_CLOTHING` | comma-separated | `filters.sizes.clothing` |
| `FILTER_SIZES_PANTS` | comma-separated | `filters.sizes.pants` |
| `FILTER_SIZES_SHOES` | comma-separated | `filters.sizes.shoes` |
| `FILTER_SIZES_ONE_SIZE` | true/false | `filters.sizes.one_size` |
| `FILTER_WATCHED_URLS` | comma-separated | `filters.watched_urls` |
| `NOTIFY_ON` | string | `notifications.notify_on` |
| `PREVIEW_CLI` | true/false | `notifications.preview_cli` |
| `PREVIEW_HTML` | true/false | `notifications.preview_html` |
| `TELEGRAM_ENABLED` | true/false | `notifications.channels.telegram.enabled` |
| `TELEGRAM_BOT_TOKEN` | string | `notifications.channels.telegram.bot_token` |
| `TELEGRAM_CHAT_ID` | string | `notifications.channels.telegram.chat_id` |
| `EMAIL_ENABLED` | true/false | `notifications.channels.email.enabled` |
| `SMTP_HOST` | string | `notifications.channels.email.smtp_host` |
| `SMTP_PORT` | int | `notifications.channels.email.smtp_port` |
| `SMTP_USE_TLS` | true/false | `notifications.channels.email.use_tls` |
| `SMTP_USER` | string | `notifications.channels.email.smtp_user` |
| `SMTP_PASSWORD` | string | `notifications.channels.email.smtp_password` |
| `SMTP_FROM` | string | `notifications.channels.email.from_address` |
| `SMTP_TO` | comma-separated | `notifications.channels.email.to_addresses` |

</details>

## Deployment

### Updating

**Docker:**

```bash
docker compose pull
docker compose up -d
```

**Git install:**

```bash
git pull
pip install -e .
sudo systemctl restart uniqlo-alerter   # if using systemd
```

### Docker tips

**Useful commands:**

```bash
docker compose logs -f              # live log output
docker compose restart              # restart after config changes
docker compose down                 # stop and remove container
```

**One-off preview** (runs a single check and exits):

```bash
docker run --rm \
  -v ./config.yaml:/app/config.yaml:ro \
  --env-file .env \
  kequach/uniqlo-sales-alerter \
  python -m uniqlo_sales_alerter --preview-cli
```

> The state file (`.seen_variants.json`) is stored in the `alerter-state` named volume so it survives container restarts and updates.

The image is available on [Docker Hub](https://hub.docker.com/r/kequach/uniqlo-sales-alerter) for `linux/amd64` and `linux/arm64`.

### Linux (systemd)

<details>
<summary><strong>Run as a systemd service on a Raspberry Pi or VPS</strong></summary>

**1. Install:**

```bash
cd /opt
sudo git clone https://github.com/kequach/uniqlo-sales-alerter.git
sudo chown -R $(whoami):$(whoami) uniqlo-sales-alerter
cd uniqlo-sales-alerter

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

**2. Configure:**

Edit `config.yaml`, then create a secrets file:

```bash
sudo nano /etc/uniqlo-sales-alerter.env
```

```ini
SMTP_USER=you@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

```bash
sudo chmod 600 /etc/uniqlo-sales-alerter.env
```

**3. Create the service:**

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
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/uniqlo-sales-alerter
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

> Change `User=pi` to your username. On a VPS this might be `ubuntu`, `deploy`, etc.

**4. Start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now uniqlo-alerter
```

**5. Manage:**

```bash
sudo systemctl status uniqlo-alerter   # check status
sudo journalctl -u uniqlo-alerter -f   # live logs
sudo systemctl restart uniqlo-alerter  # restart
```

</details>

## Preview Modes

Preview modes let you see matching deals locally without sending notifications.

```bash
python -m uniqlo_sales_alerter --preview-cli    # terminal output
python -m uniqlo_sales_alerter --preview-html   # HTML report in browser
```

Previews can also run alongside the server by setting `preview_cli: true` or `preview_html: true` in `config.yaml` (or `PREVIEW_CLI=true` / `PREVIEW_HTML=true` as env vars).

### CLI example

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
```

### HTML example

![HTML preview report](docs/img/html_preview.png)

The report includes product images, strikethrough prices with discount badges, and clickable size chips linking to in-stock variants. Dark mode is supported.

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
python -m ruff check src/ tests/
```

### How it works

The server talks to Uniqlo's internal Commerce API (the same one their website uses). On each check it queries multiple API versions and flag codes in parallel, deduplicates the results, applies your filters, verifies real-time stock per colour/size variant, and generates direct URLs to purchasable items. A persistent state file tracks which variants have already been seen so you only get notified about changes.

### Project structure

```
src/uniqlo_sales_alerter/
├── __main__.py              # CLI entry-point
├── main.py                  # FastAPI app, scheduler
├── config.py                # YAML + env var config loading
├── api/routes.py            # REST endpoints
├── clients/uniqlo.py        # Uniqlo Commerce API client
├── models/products.py       # Pydantic models
├── services/sale_checker.py # Filtering, caching, state tracking
└── notifications/
    ├── base.py              # Notifier protocol
    ├── console.py           # CLI preview
    ├── html_report.py       # HTML preview
    ├── telegram.py          # Telegram channel
    ├── email.py             # Email channel
    └── dispatcher.py        # Multi-channel dispatcher
```

## License

[MIT](LICENSE)
