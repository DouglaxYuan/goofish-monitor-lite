# Goofish Monitor Lite

English | [中文](#中文)

Goofish Monitor Lite is a lightweight second-hand marketplace price monitor for Xianyu / Goofish. It uses Playwright browser automation to reuse a user-managed login session, read marketplace search results, apply price and keyword filters, deduplicate alerts, and send local or webhook-based notifications.

This repository contains only generic source code and example configuration. Local login state, personal watchlists, private config files, logs, screenshots, and monitoring results are intentionally ignored by Git.

## Features

- Playwright-based visible login flow for SMS, QR code, or manual verification.
- Search-result monitoring with configurable product rules.
- Price band checks with low-price and suspicious-listing filters.
- Keyword include / exclude filters for cleaner alerts.
- Deduplication through local runtime state.
- Console, macOS notification, `ntfy`, webhook, and Bark notification hooks.

## Install

```bash
cd goofish-monitor-lite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Login

```bash
python goofish_monitor.py login --config config.example.json
```

The script opens a visible browser. Complete SMS verification, QR login, or any required manual check in the browser. It does not bypass captchas, anti-bot checks, or platform risk controls. After login succeeds, the browser storage state is saved locally under `state/`, which is ignored by Git.

## Monitor

```bash
python goofish_monitor.py monitor --config config.example.json
python goofish_monitor.py monitor --config config.example.json --once
```

Copy `config.example.json` to a private local config file, then edit `products`. Common product fields:

- `keyword`: search keyword.
- `target_price`: highest price that should trigger an alert.
- `min_price`: lower bound used to filter deposits, accessories, and misleading listings.
- `market_price`: reference market price for discount and suspicious-low-price checks.
- `required_any_terms`: at least one term should appear in the listing text.
- `exclude_terms`: product-specific terms to reject.

Runtime output is written to ignored local files such as `data/alerts.jsonl`, `data/market_snapshots.jsonl`, and `data/seen_items.json`.

## Filtering

Second-hand price monitoring should not rely on the lowest visible price alone. Common false positives include deposits, accessories, empty boxes, repairs, broken items, wanted posts, rentals, misleading low prices, and prices that are not actual sale prices.

The monitor filters listings in this order:

1. Price must fall between `min_price` and `target_price`.
2. Listing text must match `required_any_terms`.
3. Global or product-specific exclude terms reject a listing.
4. Prices far below `market_price * very_low_price_ratio` are penalized.
5. Suspicious phrases lower the score; listings below `default_min_score` are skipped.

## Notifications

By default, alerts are printed to the console and can be shown through macOS notifications. Optional integrations can be configured in `notifications`:

- `ntfy_topic_url`
- `webhook_url`
- `bark_url`

Keep notification URLs and tokens in private local config files, not in Git.

## Migration

The portable project files are:

- `goofish_monitor.py`
- `run_watchlist.py`
- `config.example.json`
- `requirements.txt`

On a new machine, reinstall dependencies and run `login` again if the old browser state is invalid.

## License

MIT

---

## 中文

Goofish Monitor Lite 是一个轻量版闲鱼 / Goofish 二手价格监控脚本。它使用 Playwright 浏览器自动化复用用户自己维护的登录态，读取市场搜索结果，按价格和关键词过滤，去重提醒，并通过本地通知或 webhook 发送结果。

本仓库只包含通用代码和示例配置。本地登录态、个人 watchlist、私有配置、日志、截图和监控结果都不会提交到 Git。

## 功能

- 基于 Playwright 的可见浏览器登录流程，支持短信、扫码或人工验证。
- 基于搜索结果的商品价格监控。
- 可配置价格区间，过滤定金、配件和低价引流。
- 支持关键词包含 / 排除规则。
- 使用本地运行态去重提醒。
- 支持控制台、macOS 通知、`ntfy`、webhook 和 Bark。

## 安装

```bash
cd goofish-monitor-lite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 登录

```bash
python goofish_monitor.py login --config config.example.json
```

脚本会打开可见浏览器。你可以在浏览器里完成短信验证、扫码登录或其他必要的人工验证。脚本不会绕过验证码、反爬检查或平台风控。登录成功后，浏览器状态会保存在本地 `state/` 目录，该目录已被 Git 忽略。

## 监控

```bash
python goofish_monitor.py monitor --config config.example.json
python goofish_monitor.py monitor --config config.example.json --once
```

复制 `config.example.json` 为本地私有配置文件，然后修改 `products`。常用商品字段：

- `keyword`: 闲鱼搜索词。
- `target_price`: 触发提醒的最高价格。
- `min_price`: 过滤定金、配件、低价引流等误报的最低价格。
- `market_price`: 参考市场价，用于计算折扣并识别异常低价。
- `required_any_terms`: 标题、卖家或标签里至少命中一个的产品词。
- `exclude_terms`: 当前商品额外排除词。

运行结果会写入被忽略的本地文件，例如 `data/alerts.jsonl`、`data/market_snapshots.jsonl` 和 `data/seen_items.json`。

## 过滤策略

二手价格监控不能只看最低价。常见误报包括定金、配件、包装盒、维修件、故障机、求购帖、租赁帖、低价引流，以及标价不是售价的帖子。

脚本按以下顺序过滤：

1. 价格必须在 `min_price` 和 `target_price` 之间。
2. 文本必须命中 `required_any_terms`。
3. 命中全局或商品排除词则跳过。
4. 低于 `market_price * very_low_price_ratio` 的异常低价会扣分。
5. 命中可疑文案会扣分，最终分数低于 `default_min_score` 时不提醒。

## 通知

默认会在控制台输出，也可以使用 macOS 通知中心。可在 `notifications` 中配置：

- `ntfy_topic_url`
- `webhook_url`
- `bark_url`

通知 URL 和 token 应保存在本地私有配置文件中，不要提交到 Git。

## 迁移

可迁移的核心文件：

- `goofish_monitor.py`
- `run_watchlist.py`
- `config.example.json`
- `requirements.txt`

迁移到新机器后，重新安装依赖；如果旧登录态失效，重新运行 `login`。

## 许可证

MIT
