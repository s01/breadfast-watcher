# Breadfast Telegram watcher

A credential-free catalogue watcher that sends Telegram alerts for **in-stock discounts of 50% or more**, highest percentage first. It detects newly qualifying sales and improved discounts without repeating unchanged offers. A higher reference price alone does not count as an improved deal if the actual sale price rises.

## Hosting

The GitHub Actions workflow checks every five minutes and performs a complete advertised-subcategory scan hourly. GitHub may delay or drop scheduled runs; five minutes is a target cadence, not a delivery guarantee. Standard public-repository runners are free under GitHub's current policy. No AI API, paid server, public HTTP endpoint or additional package dependencies are required.

Repository secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

The bot must first receive a message from the intended private chat. Tokens and chat IDs must never be committed. The `monitor-state` branch stores only non-personal product discount state and successful full-scan timestamps. It preserves delivered and pending offers across ephemeral runner restarts. Partial scans do not acknowledge offers, and batches are acknowledged only after Telegram confirms delivery. A timeout after Telegram accepts a message can still cause a duplicate on retry.

The initial successful delivery sends currently qualifying deals. Subsequent runs send new or improved deals, not the same unchanged list. On supported scan failures and recovery, the bot sends a status notice. GitHub/server-wide outages are not independently monitored.

## Coverage and limitations

Default coverage: **6th of October FP #6**. Other warehouses are not included. All advertised categories are checked through the observed `deals` filter; all advertised subcategories are checked hourly. The catalogue endpoints, schema and filter semantics can change.

Prices and stock are snapshots and do not reserve items. Zero sale prices are excluded because they can mean no active sale. Free promotions, account-specific coupons and checkout/payment offers are outside this monitor. It makes no purchases or account changes and uses no Breadfast credentials.

## Local commands

```sh
python3 scan.py --auto              # inspect only; no send or acknowledgment
python3 scan.py --full              # inspect every advertised subcategory
python3 run_once.py                 # send eligible alerts; needs Telegram environment variables
python3 -m unittest discover -p 'test_*.py'
```

Set `BREADFAST_STATE_DIR` to persistent storage when running outside GitHub. Docker/Compose files provide an alternative server deployment; that server is not supplied by this repository. Copy `.env.example` to `.env`, fill the two Telegram credentials, restrict permissions, and run `docker compose up -d --build`. Never commit `.env`.

To stop GitHub monitoring, disable the Breadfast Telegram watcher workflow in Actions. Rotate the Telegram token through BotFather if it is exposed.
