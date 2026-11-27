# Breadfast Local for macOS

Native **BF** menu-bar app with local notifications and a local offer/history page.
It runs independently of Codex and Telegram while the Mac is awake and online.

- Grocery/Mall prices: target polling interval 30 seconds, for **every known
  product ID**, including full-price and unavailable products. The persistent ID
  registry keeps IDs across full scans instead of forgetting disappeared items.
- Discover current campaign tabs, home/section carousels and advertised
  collections on quick checks; refresh their product IDs directly.
- Restaurant menus: 120 seconds.
- Full advertised catalogues/new-product discovery: 180 seconds, or use
  **Full scan now**. Products exposed through campaigns/collections can be found
  sooner; an unknown ID absent from these still waits for full discovery.
- Sources run independently, with one active scan per source. Restaurant latency
  cannot block grocery/Mall checks. A slow/full scan can still delay the next
  check of the same source. Polling targets are not guaranteed detection times.
- Public HTTP data uses gzip and ETags. A 304 validates the cached response;
  changed data is downloaded, and failed requests are never a successful cache
  hit. HTTP 429/503 stops queued requests and backs that source off.
- Valid products from a partially failed source can still alert. Coverage errors
  remain visible and an incomplete scan never advances full-scan success time.
- First successful full scan of each source establishes a quiet baseline.
- Baseline offers are retained in a separate permanent ledger, even after their
  discount ends. Available offers include both old and new offers; new/improved
  active offers from the last 24 hours have their own section and badge.
- A successful full scan that omits a previously available product marks it
  unverified, rather than treating absence as evidence of zero stock or no sale.
- Later new/improved available discounts ≥50% produce a grouped notification,
  with the first three products and a count. Click to view every offer.
- Separate local histories avoid interfering with the cloud bot's delivery state.
- Notification queue is acknowledged only after macOS accepts scheduling it.
  Acceptance does not guarantee a visible banner: Focus and notification settings
  can suppress presentation. Pending notices survive app restarts.
- Existing cached offers can remain until the next full scan if they disappear
  from an offers feed. Source timestamps appear on the offers page.
- No login-at-startup or sleep-prevention settings are changed. Use Pause or Quit
  in the menu to stop. After waking, the app requests a new check.

Build with the installed Swift compiler:

```sh
python3 local/build_app.py "$HOME/Applications/Breadfast Local.app"
```

Private configuration belongs in
`~/Library/Application Support/Breadfast Local/config.json`: `python` (absolute
Python 3 executable), `BREADFAST_FOOD_LATITUDE`, `BREADFAST_FOOD_LONGITUDE`.
The app bundle contains only code, never the private configuration or Telegram
credentials. Allow notifications when macOS asks.

Local data in the same private Application Support directory:

- `local-state.json`: per-source scan state, current products, pending notices,
  and complete new/improved-offer event history.
- `history.json`: complete notification-event history.
- `offer-history.json`: complete offer ledger, including baseline, historical
  imports, availability states and distinct price/status changes.
- `offers.html`: available offers, new/improved offers, unverified offers, and the
  complete ledger. It refreshes every 30 seconds. No 500-row history truncation.
- `status.json`, `app-status.json`, `worker.log`: scan/notification diagnostics.
- `status-grocery.json`, `status-mall.json`, `status-restaurants.json`: independent
  source checks, scan duration, bytes downloaded and conditional-cache hits.
- `http-cache/`: revalidated public catalogue responses, no cookies or credentials.

The scope and price rules are the same as the scanner: October FP #6 grocery,
October Mall, nearby restaurant menus for the privately configured approximate
District 5 area. Coupons, checkout promotions and other unobserved feeds are not
covered. No Telegram calls are made by this app.

Tests: `python3 -m unittest discover -s local -p 'test_*.py'`.
