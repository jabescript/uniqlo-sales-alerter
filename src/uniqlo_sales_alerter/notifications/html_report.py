"""HTML report notification channel — generates a local file and opens it in the browser."""

from __future__ import annotations

import logging
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from uniqlo_sales_alerter.models.products import SaleItem
from uniqlo_sales_alerter.notifications.base import PROJECT_URL, DealActions

logger = logging.getLogger(__name__)


def _build_report(
    deals: list[SaleItem], generated_at: datetime, server_url: str = "",
) -> str:
    """Build a self-contained HTML page styled in Uniqlo corporate identity."""
    cards: list[str] = []
    for i, deal in enumerate(deals, 1):
        watched = (
            '<span class="badge-watched">WATCHED</span>'
            if deal.is_watched else ""
        )
        img = (
            f'<img src="{deal.image_url}" alt="{deal.name}" loading="lazy"/>'
            if deal.image_url
            else '<div class="no-img">No image</div>'
        )
        actions = DealActions(deal, server_url)
        if actions.unwatch_url:
            size_parts = [
                f'<a class="size-chip" href="{url}" target="_blank">{sz}</a>'
                for sz, url in zip(deal.available_sizes, deal.product_urls)
            ]
        else:
            watch_map = dict(actions.watch_urls)
            size_parts = []
            for sz, url in zip(deal.available_sizes, deal.product_urls):
                chip = f'<a class="size-chip" href="{url}" target="_blank">{sz}</a>'
                wurl = watch_map.get(sz)
                if wurl:
                    chip += (
                        f'<a class="watch-chip" href="{wurl}" '
                        f'target="_blank" title="Watch {sz}">&#9734;</a>'
                    )
                size_parts.append(chip)
        size_links = " ".join(size_parts) or ", ".join(deal.available_sizes)

        if deal.has_known_discount:
            price_row = (
                f'<span class="price-old">{deal.currency_symbol}{deal.original_price:.2f}</span>'
                f'<span class="arrow">&rarr;</span>'
                f'<span class="price-sale">{deal.currency_symbol}{deal.sale_price:.2f}</span>'
                f'<span class="discount">-{deal.discount_percentage:.0f}%</span>'
            )
        else:
            price_row = (
                f'<span class="price-sale">{deal.currency_symbol}{deal.sale_price:.2f}</span>'
                f'<span class="discount">Sale</span>'
            )

        action_row = ""
        if actions.ignore_url:
            unwatch_btn = (
                f'<a class="action-btn action-unwatch" '
                f'href="{actions.unwatch_url}" '
                f'target="_blank">Unwatch</a>'
            ) if actions.unwatch_url else ""
            action_row = (
                '<div class="actions-row">'
                f'<a class="action-btn action-ignore" '
                f'href="{actions.ignore_url}" '
                f'target="_blank">Ignore</a>'
                + unwatch_btn
                + '</div>'
            )

        unique_colors = list(dict.fromkeys(cn for cn in deal.color_names if cn))
        color_row = (
            f'<div class="color-label">{" &middot; ".join(unique_colors)}</div>'
            if unique_colors else ""
        )

        cards.append(f"""
        <div class="card">
            <div class="card-img">{img}</div>
            <div class="card-body">
                <div class="card-title">
                    <span class="index">{i}.</span> {deal.name} {watched}
                </div>
                {color_row}
                <div class="price-row">
                    {price_row}
                </div>
                <div class="sizes">{size_links}</div>
                {action_row}
            </div>
        </div>""")

    timestamp = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>UNIQLO Sale Alert — {len(deals)} deal(s)</title>
<style>
  :root {{
    --uq-red: #ED1D24;
    --uq-dark-red: #c41219;
    --bg: #f2f2f2;
    --card-bg: #ffffff;
    --text: #333333;
    --muted: #757575;
    --border: #e0e0e0;
    --sale-green: #1a8c3a;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #191919;
      --card-bg: #2a2a2a;
      --text: #ececec;
      --muted: #999999;
      --border: #3a3a3a;
    }}
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Helvetica Neue", Helvetica, Arial,
      "Hiragino Sans", "Yu Gothic", sans-serif;
    background: var(--bg); color: var(--text);
    padding: 0; line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  /* ── Header bar ─────────────────────────────────── */
  header {{
    background: var(--uq-red); color: #fff;
    padding: 20px 24px; text-align: center;
  }}
  header .logo {{
    font-size: 1.6rem; font-weight: 800;
    letter-spacing: .12em; text-transform: uppercase;
  }}
  header .subtitle {{
    font-size: .82rem; font-weight: 400;
    opacity: .85; margin-top: 4px;
  }}

  /* ── Stats strip ────────────────────────────────── */
  .stats {{
    display: flex; justify-content: center; gap: 32px;
    padding: 14px 24px;
    background: var(--card-bg);
    border-bottom: 1px solid var(--border);
    font-size: .85rem; color: var(--muted);
  }}
  .stats strong {{ color: var(--text); }}

  /* ── Card grid ──────────────────────────────────── */
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 16px; max-width: 1240px;
    margin: 24px auto; padding: 0 24px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    display: flex; overflow: hidden;
    transition: box-shadow .15s, transform .15s;
  }}
  .card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(0,0,0,.1);
  }}

  /* ── Card image ─────────────────────────────────── */
  .card-img {{
    flex: 0 0 140px;
    display: flex; align-items: center; justify-content: center;
    background: #fafafa;
  }}
  @media (prefers-color-scheme: dark) {{
    .card-img {{ background: #222; }}
  }}
  .card-img img {{ width: 140px; height: 180px; object-fit: cover; }}
  .no-img {{
    width: 140px; height: 180px;
    display: flex; align-items: center; justify-content: center;
    color: var(--muted); font-size: .8rem;
  }}

  /* ── Card body ──────────────────────────────────── */
  .card-body {{
    padding: 14px 16px; display: flex;
    flex-direction: column; gap: 8px; flex: 1;
  }}
  .card-title {{ font-weight: 700; font-size: .92rem; }}
  .index {{ color: var(--muted); font-weight: 400; }}
  .badge-watched {{
    background: var(--uq-red); color: #fff;
    font-size: .6rem; font-weight: 800;
    letter-spacing: .04em; text-transform: uppercase;
    padding: 2px 7px; border-radius: 2px;
    vertical-align: middle; margin-left: 6px;
  }}

  /* ── Colour label ──────────────────────────────── */
  .color-label {{
    font-size: .78rem; color: var(--muted);
    font-weight: 600;
  }}

  /* ── Prices ─────────────────────────────────────── */
  .price-row {{ font-size: .93rem; }}
  .price-old {{
    text-decoration: line-through; color: var(--muted);
  }}
  .arrow {{ margin: 0 4px; color: var(--muted); }}
  .price-sale {{ color: var(--uq-red); font-weight: 700; }}
  .discount {{
    color: var(--sale-green); font-weight: 700;
    margin-left: 6px;
  }}

  /* ── Size chips ─────────────────────────────────── */
  .sizes {{
    display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto;
  }}
  .size-chip {{
    display: inline-block;
    padding: 4px 12px;
    border: 1.5px solid var(--uq-red);
    border-radius: 2px;
    color: var(--uq-red); background: transparent;
    font-size: .76rem; font-weight: 700;
    text-decoration: none; text-transform: uppercase;
    transition: background .12s, color .12s;
  }}
  .size-chip:hover {{
    background: var(--uq-red); color: #fff;
  }}

  /* ── Watch chip (per-size star) ───────────────── */
  .watch-chip {{
    display: inline-block; margin-left: 2px;
    padding: 4px 5px; font-size: .72rem;
    text-decoration: none; color: var(--muted);
    border-radius: 2px; vertical-align: middle;
    transition: color .12s;
  }}
  .watch-chip:hover {{ color: var(--uq-red); }}

  /* ── Action buttons ─────────────────────────────── */
  .actions-row {{
    display: flex; gap: 8px; margin-top: 6px;
  }}
  .action-btn {{
    display: inline-block; padding: 3px 10px;
    border-radius: 2px; font-size: .68rem; font-weight: 700;
    text-decoration: none; text-transform: uppercase;
    letter-spacing: .03em; transition: opacity .12s;
  }}
  .action-btn:hover {{ opacity: .8; }}
  .action-ignore {{
    background: var(--border); color: var(--text);
  }}
  .action-unwatch {{
    background: var(--uq-red); color: #fff;
  }}

  /* ── Footer ─────────────────────────────────────── */
  footer {{
    text-align: center; color: var(--muted);
    font-size: .72rem; padding: 24px 0 32px;
    border-top: 1px solid var(--border);
    margin: 32px 24px 0;
  }}
  footer span {{ color: var(--uq-red); font-weight: 700; }}
</style>
</head>
<body>
<header>
  <div class="logo">UNIQLO</div>
  <div class="subtitle">Sale Alert &mdash; {len(deals)} deal(s)</div>
</header>
<div class="stats">
  <span><strong>{len(deals)}</strong> matching deals</span>
  <span>Generated <strong>{timestamp}</strong></span>
</div>
<div class="grid">
{"".join(cards)}
</div>
<footer>Powered by <a href="{PROJECT_URL}"
  style="text-decoration:none;color:inherit;"><span>UNIQLO</span> Sales Alerter</a></footer>
</body>
</html>"""


class HtmlReportNotifier:
    """Generates an HTML report file and opens it in the default browser."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        output_dir: str | None = None,
        server_url: str = "",
    ) -> None:
        self._enabled = enabled
        self._output_dir = output_dir
        self._server_url = server_url

    def is_enabled(self) -> bool:
        return self._enabled

    async def send(self, deals: list[SaleItem]) -> None:
        if not deals:
            print("\n  No deals to display.\n")
            return

        now = datetime.now(timezone.utc)
        html = _build_report(deals, now, server_url=self._server_url)

        if self._output_dir:
            out = Path(self._output_dir)
        else:
            out = Path(__file__).resolve().parents[3] / "reports"
        out.mkdir(parents=True, exist_ok=True)

        stamp = now.strftime("%Y%m%d_%H%M%S")
        path = out / f"uniqlo_deals_{stamp}.html"
        path.write_text(html, encoding="utf-8")

        print(f"\n  HTML report saved to: {path}")
        webbrowser.open(path.as_uri())
        logger.info("HTML report written to %s", path)
