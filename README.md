# Breadfast Telegram discount watcher

Monitors three catalogues and sends **new or improved in-stock discounts of at least 50%**, highest percentage first:

- Grocery: October FP #6.
- Mall: the separate October Mall catalogue.
- Restaurants: menu items from restaurants returned for an approximate District 5, October area lookup. This is not a claim of citywide restaurant coverage or exact delivery eligibility.

## Schedule and controls

A free cron-job.org job dispatches `.github/workflows/watch.yml` every five minutes. GitHub's native cron trigger was removed after it produced no automatic events during verification. The watcher does not require the Mac or Codex to stay running. External outages, network failures and runner queues can delay checks.

Each regular check reads the Grocery and Mall deals feeds and all discovered nearby restaurant menus. A complete scan of the advertised Grocery and Mall subcategories is due once an hour. Grocery and Mall catalogue discovery is refreshed on each scan, and restaurant discovery follows the service's pagination on each scan.

Quick and full checks also discover every advertised `virtualCategories` campaign
and query its category/type pairs. This covers dynamically named tabs such as
Black Friday, flash deals and new arrivals without hardcoding campaign names.
Product counts are de-duplicated across feeds; these are scan counts, not counts
of qualifying discounts. The app's captured EGP 1 Nescafe product confirmed that
campaign tabs use different query types from the ordinary `deals` feed.
Quick checks additionally refresh previously known qualifying product IDs using
the app's observed indexed-ID batch endpoint. This checks a known offer even
when it is not listed in a current campaign tab. Entirely new products absent
from every advertised campaign still depend on full catalogue discovery.

The owner's private Telegram chat has **Offers scan** and **Full scan** buttons. `/offers`, `/full`, `/menu` and `/start` are also supported. Requests are polled on the next five-minute execution, receive a start reply and completion summary, and retain discount de-duplication. Offers scan covers both deals feeds plus restaurant menus; Full scan covers all three catalogues. Repeated pending taps are combined, prioritizing a full scan. Unchanged offers are not resent.

## Prices and availability

Each alert identifies the catalogue and, for restaurant items, the restaurant. English/Arabic names come from the catalogue. Prices, savings and percentages are calculated from the observed original and sale price fields. Product-photo links use observed image hosts. Open Breadfast links open the app landing page; product-specific deep links remain unverified.

A qualifying offer has positive stock, a positive sale price lower than the original price, and a discount of 50% or more. Mall items explicitly marked out of stock and items from restaurants not currently marked OPEN do not alert. Restaurant item IDs include the restaurant ID to avoid cross-restaurant collisions. Mandatory customization is flagged as a base item price whose checkout total can change.

Zero sale prices are excluded because they may mean no active sale. Order-level discounts, coupons, minimum-spend offers, payment promotions, shipping fees and optional/mandatory add-on pricing are not treated as unconditional item discounts. Prices and stock are snapshots, not reservations or guarantees of checkout price. The observed APIs and field meanings may change.

## Private configuration

GitHub Actions secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BREADFAST_FOOD_LATITUDE`
- `BREADFAST_FOOD_LONGITUDE`

Restaurant coordinates use an approximate area lookup, remain encrypted deployment configuration, and are not published in source or reports. No Breadfast login credentials are used. Only the configured private Telegram chat can trigger commands.

The external scheduler uses a fine-grained GitHub token restricted to this repository with Actions: Read and write and required Metadata: Read-only. Store it privately in cron-job.org, never in this repository. The trigger is a POST to `https://api.github.com/repos/s01/breadfast-watcher/actions/workflows/watch.yml/dispatches`, with JSON body `{"ref":"main","inputs":{"full_scan":false}}`, Content-Type `application/json`, and Accept `application/vnd.github+json`.

## Delivery and history

Separate histories are persisted on the [`monitor-state`](https://github.com/s01/breadfast-watcher/tree/monitor-state) branch:

- `telegram-state.json`: Grocery offers.
- `mall-state.json`: Mall offers.
- `restaurants-state.json`: restaurant menu offers.
- `full-scan.json`, `mall-full-scan.json`, `restaurants-full-scan.json`: successful full-scan timestamps.
- `bot-state.json`: command cursor and pending scan mode, without chat IDs or message text.
- `health-state.json`: failure/recovery notice state.

Git commits preserve revisions of qualifying-offer state, not the complete price history of all products. Each Telegram batch is compared with Telegram's returned text before its offers are acknowledged. A delivery timeout after acceptance can still cause a duplicate retry. A partial catalogue failure is reported explicitly; successfully checked catalogues may still send their offers. Requested scan completion is confirmed only after all catalogues succeed.

Workflow summaries include per-catalogue product counts, endpoint counts, delivery batch IDs, verified offer counts and errors. No new Telegram offer message is expected when there are no new qualifying offers. Inspect cron-job.org execution history and GitHub run logs to verify operation without routine Telegram spam.

## Commands

```sh
python3 scan.py --auto --catalogue grocery
python3 scan.py --full --catalogue mall
python3 scan.py --full --catalogue restaurants
python3 run_once.py
python3 -m unittest discover -p 'test_*.py'
```

Single-catalogue commands do not send or acknowledge offers unless `--telegram` is supplied. `run_once.py` checks all three and sends eligible offers. Set `BREADFAST_STATE_DIR` to persistent storage outside GitHub.

To stop monitoring, disable the cron-job.org job. Disabling the GitHub workflow prevents dispatches from running as well. Never commit `.env` or other credentials. The temporary iPhone inspection proxy is not required for deployed monitoring.
