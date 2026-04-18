"""Settings web UI — serves an HTML page for runtime configuration."""

from __future__ import annotations

import json
from typing import Any


def build_settings_page(config_data: dict[str, Any]) -> str:
    """Return a self-contained HTML settings page with *config_data* pre-populated."""
    config_json = json.dumps(config_data, indent=2).replace("</", "<\\/")
    return _TEMPLATE.replace("__CONFIG_JSON__", config_json)


_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>UNIQLO Sales Alerter — Settings</title>
<style>
  :root {
    --uq-red: #ED1D24;
    --uq-dark-red: #c41219;
    --bg: #f2f2f2;
    --card-bg: #ffffff;
    --text: #333333;
    --muted: #757575;
    --border: #e0e0e0;
    --sale-green: #1a8c3a;
    --input-bg: #ffffff;
    --input-border: #ccc;
    --sub-bg: rgba(0,0,0,.025);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #191919;
      --card-bg: #2a2a2a;
      --text: #ececec;
      --muted: #999999;
      --border: #3a3a3a;
      --input-bg: #333;
      --input-border: #555;
      --sub-bg: rgba(255,255,255,.04);
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Helvetica Neue", Helvetica, Arial,
      "Hiragino Sans", "Yu Gothic", sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Header ──────────────────────────────────── */
  header {
    background: var(--uq-red); color: #fff;
    padding: 20px 24px; text-align: center;
  }
  header .logo {
    font-size: 1.6rem; font-weight: 800;
    letter-spacing: .12em; text-transform: uppercase;
  }
  header .subtitle {
    font-size: .82rem; font-weight: 400;
    opacity: .85; margin-top: 4px;
  }

  /* ── Layout ──────────────────────────────────── */
  main {
    max-width: 740px;
    margin: 24px auto;
    padding: 0 24px 80px;
  }

  /* ── Section cards ───────────────────────────── */
  .section {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    margin-bottom: 16px;
    overflow: hidden;
  }
  .section-header {
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    font-weight: 700; font-size: .95rem;
    letter-spacing: .02em;
    text-transform: uppercase;
    color: var(--uq-red);
  }
  .section-body { padding: 20px; }

  /* ── Form fields ─────────────────────────────── */
  .field { margin-bottom: 18px; }
  .field:last-child { margin-bottom: 0; }
  .field > label {
    display: block; font-weight: 600;
    font-size: .85rem; margin-bottom: 4px;
  }
  .help {
    font-size: .75rem; color: var(--muted);
    margin-bottom: 6px; line-height: 1.4;
  }

  input[type="text"],
  input[type="number"],
  input[type="password"],
  select, textarea {
    width: 100%; padding: 9px 12px;
    border: 1px solid var(--input-border);
    border-radius: 3px;
    background: var(--input-bg);
    color: var(--text);
    font-size: .85rem; font-family: inherit;
    transition: border-color .15s, box-shadow .15s;
  }
  input:focus, select:focus, textarea:focus {
    outline: none;
    border-color: var(--uq-red);
    box-shadow: 0 0 0 2px rgba(237,29,36,.12);
  }
  textarea { resize: vertical; min-height: 80px; }
  select { cursor: pointer; }

  /* ── Checkbox group (gender) ─────────────────── */
  .checkbox-group {
    display: flex; flex-wrap: wrap; gap: 16px;
  }
  .checkbox-group label {
    display: flex; align-items: center; gap: 6px;
    font-weight: 400; font-size: .85rem; cursor: pointer;
  }

  /* ── Toggle switch ───────────────────────────── */
  .toggle-row {
    display: flex; align-items: center;
    justify-content: space-between;
    padding: 6px 0;
  }
  .toggle-label { font-weight: 600; font-size: .85rem; }
  .toggle-help { font-size: .75rem; color: var(--muted); }
  .toggle {
    position: relative; display: inline-block;
    width: 42px; height: 24px; flex-shrink: 0;
  }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .toggle .slider {
    position: absolute; cursor: pointer;
    inset: 0; background: var(--border);
    border-radius: 24px; transition: .2s;
  }
  .toggle .slider::before {
    content: ""; position: absolute;
    height: 18px; width: 18px;
    left: 3px; bottom: 3px;
    background: #fff; border-radius: 50%;
    transition: .2s;
  }
  .toggle input:checked + .slider { background: var(--uq-red); }
  .toggle input:checked + .slider::before { transform: translateX(18px); }

  /* ── Sub-section (channels) ──────────────────── */
  .subsection {
    background: var(--sub-bg);
    border: 1px solid var(--border);
    border-radius: 3px;
    padding: 16px; margin-top: 14px;
  }
  .subsection-header {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 14px;
  }
  .subsection-header .title {
    font-weight: 700; font-size: .9rem;
  }

  /* ── Size grid ───────────────────────────────── */
  .size-grid {
    display: grid; gap: 12px; margin-top: 8px;
  }
  .size-grid label {
    font-weight: 500; font-size: .8rem;
    margin-bottom: 4px; display: block;
  }

  /* ── Product list items ──────────────────────── */
  .list-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
    font-size: .84rem;
  }
  .list-item:last-child { border-bottom: none; }
  .list-item .item-name { font-weight: 600; flex: 1; }
  .list-item .item-detail { color: var(--muted); font-size: .78rem; }
  .list-item .remove-btn {
    border: none; background: none; cursor: pointer;
    color: var(--muted); font-size: 1.1rem; padding: 2px 6px;
    border-radius: 3px; transition: color .12s, background .12s;
  }
  .list-item .remove-btn:hover {
    color: var(--uq-red); background: rgba(237,29,36,.08);
  }
  .empty-msg { color: var(--muted); font-size: .82rem; font-style: italic; }

  /* ── Inline rows (quiet hours, add inputs) ──── */
  .inline-row {
    display: flex; gap: 16px;
  }
  .inline-row > * { flex: 1; min-width: 0; }
  .add-row {
    display: flex; gap: 8px; margin-top: 10px;
  }
  .add-row input { flex: 1; min-width: 0; }
  .add-row .btn { flex-shrink: 0; padding: 8px 18px; font-size: .78rem; }

  /* ── Mobile ────────────────────────────────────── */
  @media (max-width: 540px) {
    main { padding: 0 12px 90px; margin-top: 16px; }
    .section-body { padding: 14px; }
    .section-header { padding: 12px 14px; font-size: .85rem; }
    .subsection { padding: 12px; }
    .inline-row { flex-direction: column; gap: 10px; }
    .add-row { flex-direction: column; }
    .add-row .btn { width: 100%; padding: 10px; }
    .checkbox-group { gap: 10px; }
    .toggle-row { gap: 10px; }
    .list-item { font-size: .8rem; gap: 6px; }
    .list-item .item-name { word-break: break-word; }
    .list-item .item-detail { font-size: .72rem; word-break: break-all; }
    .actions .gh { position: static; margin-left: 16px; }
    .actions { justify-content: center; gap: 12px; }
    .btn { padding: 11px 28px; font-size: .82rem; }
    header { padding: 16px; }
    header .logo { font-size: 1.3rem; }
  }

  /* ── Actions ─────────────────────────────────── */
  .actions {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--card-bg);
    border-top: 1px solid var(--border);
    padding: 14px 24px;
    display: flex; align-items: center;
    justify-content: center;
    z-index: 100;
    box-shadow: 0 -2px 12px rgba(0,0,0,.06);
  }
  .actions .gh {
    position: absolute; right: 24px;
    display: inline-flex; align-items: center; gap: 5px;
    color: var(--muted); text-decoration: none;
    font-size: .78rem; font-weight: 600;
    transition: color .15s;
  }
  .actions .gh:hover { color: var(--text); }
  .actions .gh svg { fill: currentColor; }
  .btn {
    border: none; padding: 11px 40px;
    font-size: .88rem; font-weight: 700;
    letter-spacing: .04em; text-transform: uppercase;
    border-radius: 3px; cursor: pointer;
    transition: background .15s, opacity .15s;
  }
  .btn-save {
    background: var(--uq-red); color: #fff;
  }
  .btn-save:hover { background: var(--uq-dark-red); }
  .btn-save:disabled { opacity: .5; cursor: not-allowed; }

  /* ── Toast ───────────────────────────────────── */
  .toast {
    position: fixed; bottom: 80px; left: 50%;
    transform: translateX(-50%) translateY(20px);
    padding: 12px 28px; border-radius: 4px;
    font-weight: 600; font-size: .85rem;
    opacity: 0; pointer-events: none;
    transition: all .3s ease; z-index: 200;
    max-width: 90vw; text-align: center;
  }
  .toast.show {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
  }
  .toast.success { background: var(--sale-green); color: #fff; }
  .toast.error { background: var(--uq-red); color: #fff; }

</style>
</head>
<body>

<header>
  <div class="logo">UNIQLO</div>
  <div class="subtitle">Sales Alerter &mdash; Settings</div>
</header>

<main>
<form id="config-form" autocomplete="off">

  <!-- ── Watched Variants ────────────────────────── -->
  <div class="section">
    <div class="section-header">Watched Variants</div>
    <div class="section-body">
      <div class="help" style="margin-bottom:12px">
        Track specific product variants (colour + size) regardless of sale status.
        Paste a Uniqlo product URL to add, or use the Watch button in notifications.
      </div>
      <div id="watched-list"></div>
      <div class="field add-row">
        <input type="text" id="watched-add"
          placeholder="Paste a Uniqlo product URL&hellip;"/>
        <button type="button" class="btn btn-save"
          onclick="addWatchedFromUrl()">Add</button>
      </div>
    </div>
  </div>

  <!-- ── Ignored Products ────────────────────────── -->
  <div class="section">
    <div class="section-header">Ignored Products</div>
    <div class="section-body">
      <div class="help" style="margin-bottom:12px">
        Products on this list are hidden from all results (any colour/size).
        Watched variants take precedence over ignored products.
      </div>
      <div id="ignored-list"></div>
      <div class="field add-row">
        <input type="text" id="ignored-add"
          placeholder="Product URL or ID (e.g. E483049-000)"/>
        <button type="button" class="btn btn-save"
          onclick="addIgnored()">Add</button>
      </div>
    </div>
  </div>

  <!-- ── Schedule ─────────────────────────────── -->
  <div class="section">
    <div class="section-header">Schedule</div>
    <div class="section-body">

      <div class="inline-row" style="align-items:flex-start">
        <!-- Left column: periodic checks -->
        <div style="flex:1;min-width:0">
          <div class="field" style="margin-bottom:10px">
            <label for="check-interval">Periodic Checks</label>
            <div class="help">
              Runs every N minutes. Skipped during quiet hours.
              Set to <code>0</code> to disable.
            </div>
            <input type="number" id="check-interval" min="0" step="1"
              placeholder="30"/>
          </div>

          <div class="toggle-row" style="padding:2px 0 6px">
            <div>
              <span class="toggle-label">Quiet Hours</span>
              <div class="toggle-help">
                Suppress periodic checks during this window.
              </div>
            </div>
            <label class="toggle">
              <input type="checkbox" id="quiet-hours-enabled"/>
              <span class="slider"></span>
            </label>
          </div>

          <div class="inline-row" style="gap:10px">
            <div>
              <label for="quiet-hours-start">Start</label>
              <input type="text" id="quiet-hours-start" placeholder="01:00" maxlength="5"/>
            </div>
            <div>
              <label for="quiet-hours-end">End</label>
              <input type="text" id="quiet-hours-end" placeholder="08:00" maxlength="5"/>
            </div>
          </div>
          <div class="help" style="margin-top:2px">
            24-hour HH:MM. May cross midnight.
          </div>
        </div>

        <!-- Right column: scheduled checks -->
        <div style="flex:1;min-width:0">
          <div class="field">
            <label for="scheduled-checks">Scheduled Checks</label>
            <div class="help">
              Fixed daily times (24-hour HH:MM, one per line).
              Always runs &mdash; <strong>not</strong> affected by quiet hours.
              Both modes can be used together; a recent scheduled check
              automatically skips the next periodic one.
            </div>
            <textarea id="scheduled-checks" rows="4"
              placeholder="12:00&#10;16:00&#10;20:00"></textarea>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- ── General ─────────────────────────────── -->
  <div class="section">
    <div class="section-header">General</div>
    <div class="section-body">

      <div class="field">
        <label for="country">Country / Language</label>
        <div class="help">
          Region for the Uniqlo API. Full-support countries provide original prices
          and discount percentages. Limited-support countries show sale-flagged
          items but <code>min_sale_percentage</code> is ignored.
        </div>
        <select id="country">
          <optgroup label="Full Support">
            <option value="de/de">Germany (de/de)</option>
            <option value="uk/en">United Kingdom (uk/en)</option>
            <option value="fr/fr">France (fr/fr)</option>
            <option value="es/es">Spain (es/es)</option>
            <option value="it/it">Italy (it/it)</option>
            <option value="be/fr">Belgium — FR (be/fr)</option>
            <option value="be/nl">Belgium — NL (be/nl)</option>
            <option value="nl/nl">Netherlands (nl/nl)</option>
            <option value="dk/en">Denmark (dk/en)</option>
            <option value="se/en">Sweden (se/en)</option>
            <option value="au/en">Australia (au/en)</option>
            <option value="in/en">India (in/en)</option>
            <option value="id/en">Indonesia (id/en)</option>
            <option value="vn/vi">Vietnam (vn/vi)</option>
            <option value="ph/en">Philippines (ph/en)</option>
            <option value="my/en">Malaysia (my/en)</option>
            <option value="th/en">Thailand (th/en)</option>
          </optgroup>
          <optgroup label="Limited Support (no discount %)">
            <option value="us/en">United States (us/en)</option>
            <option value="ca/en">Canada (ca/en)</option>
            <option value="jp/ja">Japan (jp/ja)</option>
            <option value="kr/ko">South Korea (kr/ko)</option>
            <option value="sg/en">Singapore (sg/en)</option>
          </optgroup>
        </select>
      </div>

      <div class="field">
        <label for="server-url">Server URL</label>
        <div class="help">
          Host URL of this server for action buttons (Ignore / Watch) in notifications.
          Use <code>http://localhost</code> if you only access notifications on this machine,
          or a LAN IP like <code>http://192.168.1.50</code> for other devices on your network.
          Leave empty to hide action buttons. The port is appended automatically.
        </div>
        <input type="text" id="server-url" placeholder="http://localhost"/>
      </div>

      <div class="field">
        <label for="port">Port</label>
        <div class="help">
          Port the server listens on. Default: <code>8000</code>.
        </div>
        <input type="number" id="port" placeholder="8000" min="1" max="65535"/>
      </div>

    </div>
  </div>

  <!-- ── Filters ───────────────────────────────── -->
  <div class="section">
    <div class="section-header">Filters</div>
    <div class="section-body">

      <div class="field">
        <label>Gender</label>
        <div class="help">Which categories to include in sale checks.</div>
        <div class="checkbox-group">
          <label><input type="checkbox" name="gender" value="men"/> Men</label>
          <label><input type="checkbox" name="gender" value="women"/> Women</label>
          <label><input type="checkbox" name="gender" value="unisex"/> Unisex</label>
          <label><input type="checkbox" name="gender" value="kids"/> Kids</label>
          <label><input type="checkbox" name="gender" value="baby"/> Baby</label>
        </div>
      </div>

      <div class="field">
        <label for="min-sale">Minimum Sale Percentage</label>
        <div class="help">
          Only surface items with at least this discount. Ignored for limited-support countries
          where the API doesn&rsquo;t expose original prices.
        </div>
        <input type="number" id="min-sale" min="0" max="100" step="1"/>
      </div>

      <div class="field">
        <label>Size Filters</label>
        <div class="help">
          Only show items available in at least one of these sizes.
          Leave a field empty to skip filtering for that category.
          Comma-separated.
        </div>
        <div class="size-grid">
          <div>
            <label for="sizes-clothing">Clothing (XXS, XS, S, M, L, XL, XXL, 3XL)</label>
            <input type="text" id="sizes-clothing" placeholder="e.g. S, M, L"/>
          </div>
          <div>
            <label for="sizes-pants">Pants (22inch – 40inch)</label>
            <input type="text" id="sizes-pants" placeholder="e.g. 30inch, 31inch, 32inch"/>
          </div>
          <div>
            <label for="sizes-shoes">Shoes (37 – 43)</label>
            <input type="text" id="sizes-shoes" placeholder="e.g. 42, 42.5, 43"/>
          </div>
          <div class="toggle-row" style="margin-top:4px">
            <div>
              <span class="toggle-label">Include one-size items</span>
              <div class="toggle-help">Bags, hats, accessories, etc.</div>
            </div>
            <label class="toggle">
              <input type="checkbox" id="sizes-one-size"/>
              <span class="slider"></span>
            </label>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- ── Notifications ─────────────────────────── -->
  <div class="section">
    <div class="section-header">Notifications</div>
    <div class="section-body">

      <div class="field">
        <div class="toggle-row">
          <div>
            <span class="toggle-label">CLI Preview</span>
            <div class="toggle-help">Print matched deals to the terminal.</div>
          </div>
          <label class="toggle">
            <input type="checkbox" id="preview-cli"/>
            <span class="slider"></span>
          </label>
        </div>
        <div class="toggle-row" style="margin-top:6px">
          <div>
            <span class="toggle-label">HTML Preview</span>
            <div class="toggle-help">Generate an HTML report and open it in the browser.</div>
          </div>
          <label class="toggle">
            <input type="checkbox" id="preview-html"/>
            <span class="slider"></span>
          </label>
        </div>
      </div>

      <div class="field">
        <label for="notify-on">Notification Mode</label>
        <div class="help">Controls which deals trigger a notification.</div>
        <select id="notify-on">
          <option value="all_then_new">All then New &mdash; first check all, then new only</option>
          <option value="new_deals">New Deals &mdash; only previously-unseen variants</option>
          <option value="every_check">Every Check &mdash; all matching deals every time</option>
        </select>
      </div>

      <!-- Telegram -->
      <div class="subsection">
        <div class="subsection-header">
          <label class="toggle">
            <input type="checkbox" id="telegram-enabled"/>
            <span class="slider"></span>
          </label>
          <span class="title">Telegram</span>
        </div>
        <div class="field">
          <label for="telegram-token">Bot Token</label>
          <input type="password" id="telegram-token" autocomplete="off"/>
        </div>
        <div class="field">
          <label for="telegram-chat-id">Chat ID</label>
          <input type="text" id="telegram-chat-id"/>
        </div>
      </div>

      <!-- Email / SMTP -->
      <div class="subsection">
        <div class="subsection-header">
          <label class="toggle">
            <input type="checkbox" id="email-enabled"/>
            <span class="slider"></span>
          </label>
          <span class="title">Email (SMTP)</span>
        </div>
        <div class="field">
          <label for="smtp-host">SMTP Host</label>
          <input type="text" id="smtp-host"/>
        </div>
        <div class="field">
          <label for="smtp-port">SMTP Port</label>
          <input type="number" id="smtp-port" min="1" max="65535"/>
        </div>
        <div class="toggle-row field">
          <span class="toggle-label">Use TLS</span>
          <label class="toggle">
            <input type="checkbox" id="smtp-tls"/>
            <span class="slider"></span>
          </label>
        </div>
        <div class="field">
          <label for="smtp-user">SMTP User</label>
          <input type="text" id="smtp-user"/>
        </div>
        <div class="field">
          <label for="smtp-password">SMTP Password</label>
          <input type="password" id="smtp-password" autocomplete="off"/>
        </div>
        <div class="field">
          <label for="smtp-from">From Address</label>
          <input type="text" id="smtp-from" placeholder="alerts@example.com"/>
        </div>
        <div class="field">
          <label for="smtp-to">To Addresses</label>
          <div class="help">One email address per line.</div>
          <textarea id="smtp-to" rows="2" placeholder="recipient@example.com"></textarea>
        </div>
      </div>

    </div>
  </div>

  <!-- ── Sale Category Paths ─────────────────── -->
  <div class="section">
    <div class="section-header">Sale Category Paths (Singapore only)</div>
    <div class="section-body">

      <div class="field">
        <label for="sale-paths">Path IDs</label>
        <div class="help">
          Optional category path IDs, comma-separated. Some countries (e.g.&nbsp;Singapore)
          organise sale items into paths instead of tagging them.
          Find yours in the sale-page URL: <code>…/feature/sale/men?path=<b>5856</b></code>
        </div>
        <input type="text" id="sale-paths" placeholder="e.g. 5855, 5856, 5857, 5858"/>
      </div>

    </div>
  </div>

</form>
</main>

<div class="actions">
  <button type="submit" form="config-form" class="btn btn-save" id="save-btn">
    Save &amp; Reload
  </button>
  <a class="gh" href="https://github.com/kequach/uniqlo-sales-alerter"
     target="_blank" rel="noopener">
    <svg width="16" height="16" viewBox="0 0 16 16"><path d="M8 0C3.58 0 0
 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17
.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49
-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68
-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87
.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64
-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36
-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1
 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2
-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82
 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54
 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55
.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"
    /></svg>
    GitHub
  </a>
</div>

<div id="toast" class="toast"></div>

<script type="application/json" id="config-data">__CONFIG_JSON__</script>
<script>
(function () {
  "use strict";
  var CONFIG = JSON.parse(document.getElementById("config-data").textContent);

  /* ── helpers ─────────────────────────────────── */
  function splitCSV(s)   { return s.split(",").map(function(v){return v.trim()}).filter(Boolean); }
  function splitLines(s) {
    return s.split("\\n").map(function(v){return v.trim()}).filter(Boolean);
  }
  function $(id)         { return document.getElementById(id); }
  function val(id)       { return $(id).value; }
  function checked(id)   { return $(id).checked; }

  var _TIME_RE = /^([01]?\\d|2[0-3]):[0-5]\\d$/;
  function validateScheduledChecks() {
    var lines = splitLines(val("scheduled-checks"));
    for (var i = 0; i < lines.length; i++) {
      if (!_TIME_RE.test(lines[i])) {
        showToast("Invalid scheduled check time: '" + lines[i]
          + "' — use 24-hour HH:MM format (e.g. 12:00)", "error");
        return false;
      }
    }
    return true;
  }

  function showToast(msg, type) {
    var el = $("toast");
    el.textContent = msg;
    el.className = "toast " + type + " show";
    clearTimeout(el._tid);
    el._tid = setTimeout(function () { el.className = "toast"; }, 4000);
  }

  /* ── watched / ignored list state ─────────────── */
  var _watchedVariants = [];
  var _ignoredProducts = [];

  function renderWatchedList(items) {
    _watchedVariants = items || [];
    var el = $("watched-list");
    if (!_watchedVariants.length) {
      el.innerHTML = '<div class="empty-msg">No watched variants.</div>';
      return;
    }
    el.innerHTML = _watchedVariants.map(function(w, i) {
      var title = w.name || w.id;
      var colorStr = w.color_name
        ? w.color + " " + w.color_name : (w.color || "\u2014");
      var sizeStr = w.size_name || w.size || "\u2014";
      var urlLink = w.url
        ? ' <a href="' + w.url + '" target="_blank" '
          + 'style="color:var(--muted);font-size:.72rem">\u2197</a>'
        : "";
      return '<div class="list-item">' +
        '<div style="flex:1;min-width:0">' +
          '<div class="item-name">' + title + urlLink + '</div>' +
          '<div class="item-detail">' + w.id +
            ' &middot; ' + colorStr +
            ' &middot; ' + sizeStr + '</div>' +
        '</div>' +
        '<button type="button" class="remove-btn" ' +
        'onclick="removeWatched(' + i + ')">&times;</button>' +
        '</div>';
    }).join("");
  }

  function renderIgnoredList(items) {
    _ignoredProducts = items || [];
    var el = $("ignored-list");
    if (!_ignoredProducts.length) {
      el.innerHTML = '<div class="empty-msg">No ignored products.</div>';
      return;
    }
    el.innerHTML = _ignoredProducts.map(function(p, i) {
      var title = p.name || p.id;
      var urlLink = p.url
        ? ' <a href="' + p.url + '" target="_blank" '
          + 'style="color:var(--muted);font-size:.72rem">\u2197</a>'
        : "";
      var detail = p.name ? p.id : "";
      return '<div class="list-item">' +
        '<div style="flex:1;min-width:0">' +
          '<div class="item-name">' + title + urlLink + '</div>' +
          (detail
            ? '<div class="item-detail">' + detail + '</div>'
            : '') +
        '</div>' +
        '<button type="button" class="remove-btn" ' +
        'onclick="removeIgnored(' + i + ')">&times;</button>' +
        '</div>';
    }).join("");
  }

  function _saveConfig(onFinally) {
    fetch("/api/v1/config", {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(collect())
    })
    .then(function (res) {
      if (!res.ok) return res.json().then(function (j) {
        throw new Error(j.detail || "Save failed");
      });
      return res.json();
    })
    .then(function (data) {
      showToast("Saved & reloaded!", "success");
      if (data.config) { CONFIG = data.config; populate(CONFIG); }
    })
    .catch(function (err) {
      showToast("Error: " + err.message, "error");
    })
    .finally(onFinally || function(){});
  }

  window.removeWatched = function(i) {
    _watchedVariants.splice(i, 1);
    renderWatchedList(_watchedVariants);
    _saveConfig();
  };
  window.removeIgnored = function(i) {
    _ignoredProducts.splice(i, 1);
    renderIgnoredList(_ignoredProducts);
    _saveConfig();
  };

  function _parseProductUrl(raw) {
    var u = new URL(raw);
    var parts = u.pathname.split("/").filter(Boolean);
    var pid = "", pg = "00", j = 0;
    for (; j < parts.length; j++) {
      if (parts[j] === "products" && j + 1 < parts.length) {
        pid = parts[j+1];
        if (j + 2 < parts.length) pg = parts[j+2];
        break;
      }
    }
    return { pid: pid, pg: pg, params: new URLSearchParams(u.search) };
  }

  function _verifyAndAdd(productId, onSuccess) {
    fetch("/api/v1/products/" + encodeURIComponent(productId) + "/verify")
    .then(function (res) {
      if (!res.ok) return res.json().then(function (j) {
        throw new Error(j.detail || "Product not found");
      });
      return res.json();
    })
    .then(onSuccess)
    .catch(function (err) {
      showToast(err.message, "error");
    });
  }

  window.addWatchedFromUrl = function() {
    var raw = val("watched-add").trim();
    if (!raw) return;
    try {
      var parsed = _parseProductUrl(raw);
      if (!parsed.pid) {
        showToast("Could not extract product ID from URL", "error");
        return;
      }
      _verifyAndAdd(parsed.pid, function(data) {
        _watchedVariants.push({
          url: raw,
          id: parsed.pid,
          price_group: parsed.pg,
          name: data.name || "",
          color: parsed.params.get("colorDisplayCode") || "",
          color_name: "",
          size: parsed.params.get("sizeDisplayCode") || "",
          size_name: ""
        });
        renderWatchedList(_watchedVariants);
        $("watched-add").value = "";
        _saveConfig();
      });
    } catch(e) {
      showToast("Invalid URL", "error");
    }
  };

  window.addIgnored = function() {
    var raw = val("ignored-add").trim();
    if (!raw) return;
    var id = raw;
    if (raw.startsWith("http")) {
      try {
        var parsed = _parseProductUrl(raw);
        if (parsed.pid) id = parsed.pid;
      } catch(e) { /* treat as plain ID */ }
    }
    _verifyAndAdd(id, function(data) {
      _ignoredProducts.push({ id: id, name: data.name || "", url: "" });
      renderIgnoredList(_ignoredProducts);
      $("ignored-add").value = "";
      _saveConfig();
    });
  };

  /* ── populate form from config ───────────────── */
  function populate(cfg) {
    $("country").value = cfg.uniqlo.country;
    $("check-interval").value = cfg.uniqlo.check_interval_minutes;
    $("scheduled-checks").value = (cfg.uniqlo.scheduled_checks || []).join("\\n");
    $("sale-paths").value = (cfg.uniqlo.sale_paths || []).join(", ");

    var genders = (cfg.filters.gender || []).map(function(g){return g.toLowerCase()});
    document.querySelectorAll('input[name="gender"]').forEach(function (cb) {
      cb.checked = genders.indexOf(cb.value) !== -1;
    });
    $("min-sale").value = cfg.filters.min_sale_percentage;

    var sz = cfg.filters.sizes || {};
    $("sizes-clothing").value = (sz.clothing || []).join(", ");
    $("sizes-pants").value    = (sz.pants    || []).join(", ");
    $("sizes-shoes").value    = (sz.shoes    || []).join(", ");
    $("sizes-one-size").checked = !!sz.one_size;

    renderWatchedList(cfg.filters.watched_variants || []);
    renderIgnoredList(cfg.filters.ignored_products || []);

    $("server-url").value = cfg.server_url || "";
    $("port").value = cfg.port || 8000;

    var qh = cfg.quiet_hours || {};
    $("quiet-hours-enabled").checked = !!qh.enabled;
    $("quiet-hours-start").value     = qh.start || "01:00";
    $("quiet-hours-end").value       = qh.end   || "08:00";

    $("preview-cli").checked  = !!cfg.notifications.preview_cli;
    $("preview-html").checked = !!cfg.notifications.preview_html;
    $("notify-on").value      = cfg.notifications.notify_on;

    var tg = cfg.notifications.channels.telegram;
    $("telegram-enabled").checked = !!tg.enabled;
    $("telegram-token").value     = tg.bot_token || "";
    $("telegram-chat-id").value   = tg.chat_id   || "";

    var em = cfg.notifications.channels.email;
    $("email-enabled").checked = !!em.enabled;
    $("smtp-host").value       = em.smtp_host     || "";
    $("smtp-port").value       = em.smtp_port     || 587;
    $("smtp-tls").checked      = em.use_tls !== false;
    $("smtp-user").value       = em.smtp_user     || "";
    $("smtp-password").value   = em.smtp_password || "";
    $("smtp-from").value       = em.from_address  || "";
    $("smtp-to").value         = (em.to_addresses  || []).join("\\n");
  }

  /* ── collect form data ───────────────────────── */
  function collect() {
    var genders = [];
    document.querySelectorAll('input[name="gender"]:checked').forEach(function (cb) {
      genders.push(cb.value);
    });
    return {
      uniqlo: {
        country: val("country"),
        check_interval_minutes: parseInt(val("check-interval"), 10),
        scheduled_checks: splitLines(val("scheduled-checks")),
        sale_paths: splitCSV(val("sale-paths"))
      },
      server_url: val("server-url"),
      port: parseInt(val("port")) || 8000,
      quiet_hours: {
        enabled: checked("quiet-hours-enabled"),
        start:   val("quiet-hours-start") || "01:00",
        end:     val("quiet-hours-end")   || "08:00"
      },
      filters: {
        gender: genders,
        min_sale_percentage: parseFloat(val("min-sale")) || 0,
        sizes: {
          clothing: splitCSV(val("sizes-clothing")),
          pants:    splitCSV(val("sizes-pants")),
          shoes:    splitCSV(val("sizes-shoes")),
          one_size: checked("sizes-one-size")
        },
        watched_variants: _watchedVariants,
        ignored_products: _ignoredProducts
      },
      notifications: {
        preview_cli:  checked("preview-cli"),
        preview_html: checked("preview-html"),
        notify_on:    val("notify-on"),
        channels: {
          telegram: {
            enabled:   checked("telegram-enabled"),
            bot_token: val("telegram-token"),
            chat_id:   val("telegram-chat-id")
          },
          email: {
            enabled:      checked("email-enabled"),
            smtp_host:    val("smtp-host"),
            smtp_port:    parseInt(val("smtp-port"), 10) || 587,
            use_tls:      checked("smtp-tls"),
            smtp_user:    val("smtp-user"),
            smtp_password:val("smtp-password"),
            from_address: val("smtp-from"),
            to_addresses: splitLines(val("smtp-to"))
          }
        }
      }
    };
  }

  /* ── form submit ─────────────────────────────── */
  $("config-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!validateScheduledChecks()) return;
    var btn = $("save-btn");
    btn.disabled = true;
    btn.textContent = "Saving\\u2026";
    _saveConfig(function () {
      btn.disabled = false;
      btn.textContent = "Save & Reload";
    });
  });

  /* ── init ────────────────────────────────────── */
  populate(CONFIG);
})();
</script>
</body>
</html>
"""
