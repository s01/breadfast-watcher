# Breadfast Telegram watcher

A credential-free catalogue watcher that sends Telegram alerts for **in-stock discounts of 50% or more**, highest percentage first. It detects newly qualifying sales and improved discounts without repeating unchanged offers. A higher reference price alone does not count as an improved deal if the actual sale price rises.

## Hosting

A free cron-job.org job triggers the GitHub Actions workflow every five minutes through its workflow-dispatch endpoint. The scanner performs a complete advertised-subcategory scan hourly. The external scheduler replaces GitHub's native cron trigger, which did not produce automatic events during verification. The five-minute cadence is a target; external service outages and GitHub runner queues can delay execution. Standard public-repository runners are free under GitHub's current policy. No AI API, paid server, public HTTP endpoint or additional package dependencies are required.

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

To stop monitoring, disable the cron-job.org job. Disabling the GitHub Actions workflow also prevents dispatches from running. Rotate the Telegram token through BotFather if it is exposed.

## Messages and saved history

Alerts use Telegram HTML formatting with four products per message, exact catalogue names in English and Arabic, discount rounded to one decimal, original price, sale price and savings. The Open Breadfast link opens the app landing page; search for the displayed product name. Product-photo links point to the actual catalogue image. A verified product-specific deep link has not been found, so these links are deliberately not labelled as direct product links.

History is stored on the [`monitor-state`](https://github.com/s01/breadfast-watcher/tree/monitor-state) branch. `telegram-state.json` contains observed qualifying offers and the last delivered offer for each tracked product. Git commits preserve revisions of that state. `full-scan.json` contains the latest successful full-scan timestamp, and `health-state.json` tracks failure/recovery notices. GitHub Actions logs contain scan summaries. This is alert-state history, not a complete historical database of every product's price on every scan.


## External scheduler configuration

Use a cron-job.org job with a five-minute schedule, POST request method, and URL `https://api.github.com/repos/s01/breadfast-watcher/actions/workflows/watch.yml/dispatches`. Set `Content-Type: application/json` and `Accept: application/vnd.github+json`, and use the body `{"ref":"main","inputs":{"full_scan":false}}`. Authentication uses a fine-grained GitHub token restricted to this repository with **Actions: Read and write** and required **Metadata: Read-only**. Store that token privately in the scheduler's Authorization header; never commit it.

The scheduler's execution history verifies actual timed requests. GitHub's `workflow_dispatch` events then verify scanner execution. No Telegram message is expected when there are no new qualifying offers. Each sent batch is checked against Telegram's returned text before its offers are acknowledged. Workflow summaries include delivered message and offer counts, product IDs per batch, and content-verification results.
