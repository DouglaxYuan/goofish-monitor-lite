# Goofish Monitor Lite

[English](#english)

- **项目状态**：可用，维护中
- **当前版本**：0.2.0
- **最后验证**：2026-07-18

Goofish Monitor Lite 是一个轻量级闲鱼 / Goofish 二手价格监控工具。它适合关注相机、镜头、硬盘、电脑配件、收藏品等价格波动的人：你给它一组搜索词、目标价格和过滤规则，它会定时打开闲鱼搜索页，读取搜索结果，过滤掉定金、配件、故障件、低价引流等误报，再把值得人工复核的候选商品提醒给你。

它的目标不是“全自动下单”，而是把每天反复搜索、比价、排除明显误报这类机械步骤交给脚本，让人只处理真正值得看的少量候选。对日常生活来说，它能减少蹲闲鱼的时间，避免错过接近目标价的好货，也降低被异常低价和标题党干扰的概率。

本仓库只包含通用代码和示例配置。本地登录态、个人 watchlist、私有配置、通知 URL、日志、截图和监控结果都不会提交到 Git。

## 适合谁使用

- 已经明确目标型号和心理价位，但不想每天重复搜索闲鱼的人。
- 愿意人工判断卖家、成色和交易风险，只希望脚本减少低质量候选的人。
- 能在首次运行时自己完成短信、扫码或平台要求的人工登录验证的人。

不适合自动抢购、绕过验证码或风控、批量抓取平台数据，也不能替代验机、信用判断和交易担保。脚本发出提醒只代表“满足过滤条件”，不代表商品真实可靠。

## 使用链路

```text
用户配置关键词与价格
  → 人工完成闲鱼登录
  → Playwright 读取搜索结果
  → 价格与关键词规则过滤
  → 本地去重
  → 推送少量待人工复核商品
```

## 它能做什么

- 使用 Playwright 打开真实浏览器，复用用户自己完成的闲鱼登录态。
- 按配置搜索一个或多个商品关键词。
- 从搜索接口响应优先读取结构化结果，失败时再回退到页面 DOM。
- 依据 `target_price`、`min_price`、`market_price`、关键词和排除词过滤候选。
- 自动过滤常见误报：定金、配件、维修件、故障件、包装盒、求购帖、租赁帖、低价引流、标价不是售价。
- 通过本地状态文件记录已提醒商品，避免同一商品反复打扰。
- 支持控制台、macOS 通知、`ntfy`、通用 webhook、Bark 和 Server 酱推送。

## 技术框架

- **Python 3**：主程序和调度脚本。
- **Playwright**：浏览器自动化、登录态复用、搜索页访问和接口响应监听。
- **requests**：发送 webhook、Bark、Server 酱等 HTTP 通知。
- **本地 JSON 文件**：保存配置、登录态、去重状态和监控结果。

项目没有数据库和后端服务，适合放在 Mac、Linux 小主机、OpenClaw、NAS 容器或其他 agent 工作区里运行。

## 目录和关键文件

| 文件 | 作用 |
| --- | --- |
| `goofish_monitor.py` | 核心监控脚本，负责登录、搜索、过滤、去重和通知 |
| `run_watchlist.py` | 批量运行多个本地配置文件的调度入口 |
| `push_serverchan.py` | Server 酱微信推送工具，可单独使用 |
| `config.example.json` | 安全示例配置，不包含个人手机号、商品偏好或 token |
| `requirements.txt` | Python 依赖 |
| `.gitignore` | 排除本地登录态、个人配置、日志和运行结果 |

## 快速开始

```bash
git clone https://github.com/DouglaxYuan/goofish-monitor-lite.git
cd goofish-monitor-lite

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

复制示例配置：

```bash
cp config.example.json config.local.json
```

编辑 `config.local.json`：

```json
{
  "account": {
    "phone": "YOUR_PHONE_NUMBER",
    "storage_state": "state/goofish_state.json"
  },
  "products": [
    {
      "name": "Example Camera Gear",
      "keyword": "Example Camera Gear",
      "target_price": 1000,
      "min_price": 300,
      "market_price": 1500,
      "required_any_terms": ["Example", "Camera", "Gear"],
      "exclude_terms": ["accessory", "parts", "repair"]
    }
  ]
}
```

首次登录：

```bash
python goofish_monitor.py login --config config.local.json
```

脚本会打开可见浏览器。请在浏览器里完成短信验证、扫码登录或其他人工验证。脚本不会绕过验证码、反爬检查或平台风控。登录成功后，浏览器状态会保存在 `state/goofish_state.json`，该文件不会提交到 Git。

单次监控：

```bash
python goofish_monitor.py monitor --config config.local.json --once
```

持续监控：

```bash
python goofish_monitor.py monitor --config config.local.json
```

## 需要用户提供什么

必须提供：

- `account.phone`：用于辅助打开登录流程的手机号。也可以留空，手动在浏览器里登录。
- `products[].keyword`：闲鱼搜索词。
- `products[].target_price`：触发提醒的最高价格。
- `products[].min_price`：过滤异常低价、定金和配件的最低价格。
- `products[].required_any_terms`：标题或商品文本里至少需要出现的关键词。

建议提供：

- `products[].market_price`：你心中的市场价，用来判断折扣和异常低价。
- `products[].exclude_terms`：当前商品额外排除词。
- `runtime.interval_seconds`：持续监控间隔。
- `runtime.jitter_seconds`：随机延迟，避免固定频率访问。

通知配置可选：

- `notifications.ntfy_topic_url`
- `notifications.webhook_url`
- `notifications.bark_url`

Server 酱可用环境变量：

```bash
export SERVERCHAN_SENDKEY="SCTxxxxxxxx"
python push_serverchan.py "标题" "正文 markdown"
```

不要把真实手机号、通知 URL、SendKey、登录态或 watchlist 提交到 Git。建议使用 `config.local.json`、`watchlist.json` 和环境变量保存这些信息。

## 配置字段说明

### `account`

- `phone`: 登录手机号。用于辅助填入登录页；不用于绕过验证。
- `storage_state`: Playwright 登录态保存路径，默认 `state/goofish_state.json`。
- `login_screenshot`: 登录时截图保存路径，方便远程环境观察进度。
- `headless`: 是否无头运行。首次登录建议 `false`。
- `slow_mo_ms`: 浏览器动作延迟，适当模拟人工操作节奏。

### `runtime`

- `interval_seconds`: 持续监控的轮询间隔。
- `jitter_seconds`: 每轮随机延迟。
- `max_pages`: 搜索页数。
- `max_results_per_product`: 每个商品最多处理多少条结果。
- `page_timeout_ms`: 页面超时时间。
- `stop_on_risk_control`: 遇到风控或登录页时停止，避免无意义请求。

### `filters`

- `global_exclude_terms`: 全局排除词。
- `suspicious_terms`: 可疑文案，命中后会扣分。
- `default_min_score`: 低于该分数不提醒。
- `very_low_price_ratio`: 低于市场价某一比例时视作异常低价。

### `products`

- `name`: 商品名称，用于日志和提醒。
- `keyword`: 搜索词。
- `target_price`: 最高提醒价。
- `min_price`: 最低有效价。
- `market_price`: 参考市场价。
- `required_any_terms`: 至少命中一个的正向关键词。
- `exclude_terms`: 当前商品排除词。
- `max_results`: 当前商品每轮最多处理的搜索结果。

## 给 OpenClaw / agent 的快速启动说明

把下面这段交给 OpenClaw、Codex、Claude Code 或其他 agent 即可：

```text
这是一个 Python + Playwright 的闲鱼价格监控项目。请在仓库根目录创建虚拟环境，安装 requirements.txt，并运行 `python -m playwright install chromium`。复制 `config.example.json` 为 `config.local.json`，把 account.phone、products[].keyword、target_price、min_price、market_price、required_any_terms 改成用户提供的值。首次运行 `python goofish_monitor.py login --config config.local.json`，让用户在可见浏览器里完成人工登录。登录成功后运行 `python goofish_monitor.py monitor --config config.local.json --once` 做单次测试；确认结果正常后再去掉 `--once` 持续运行。不要提交 state/、data/、logs/、reports/、config.local.json、watchlist.json，也不要输出或记录用户 token、cookie、通知 URL。
```

如果 agent 只需要最低成本跑通：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp config.example.json config.local.json
python goofish_monitor.py login --config config.local.json
python goofish_monitor.py monitor --config config.local.json --once
```

## 隐私和安全边界

- 本项目不会帮你绕过验证码或平台风控。
- 本项目不会自动购买商品。
- 登录态只保存在你的本机 `state/` 目录。
- 私有配置、watchlist、日志、截图和监控结果默认被 `.gitignore` 排除。
- 公开仓库里只保留通用代码和示例配置。

## 日常检查与成功标准

| 操作 | 成功标志 |
|---|---|
| 首次登录 | 本地生成受忽略的浏览器状态，后续访问不再跳回登录页 |
| 单次监控 | 完成一轮搜索并输出候选数量或明确的零结果 |
| 持续监控 | 按配置间隔运行，重复商品不会反复提醒 |
| 通知测试 | 目标通知渠道收到脱敏测试消息 |

## 已知限制

- 闲鱼页面、接口和风控策略会变化，脚本可能需要随平台更新调整。
- 价格和关键词过滤只能减少误报，无法判断卖家诚信、商品真伪和实际成色。
- 持续监控应使用合理间隔与随机延迟；遇到登录失效或风控时应停止并人工处理。
- macOS 以外的平台通知能力可能不同，至少应保留控制台输出作为验证依据。

## 文档导航

- [Agent 快速启动](docs/AGENT_QUICKSTART.md)
- [安全示例配置](config.example.json)
- [版本记录](CHANGELOG.md)
- [许可证](LICENSE)

## License

MIT

---

## English

Goofish Monitor Lite is a lightweight second-hand marketplace price monitor for Xianyu / Goofish. It is useful when you track camera gear, lenses, drives, computer parts, collectibles, or any item whose second-hand price changes often. You provide search keywords, target prices, and filtering rules. The script opens Goofish search pages, reads listing results, removes obvious false positives such as deposits, accessories, broken items, and misleading low-price posts, then notifies you about the small set of listings worth manual review.

The goal is not automatic purchasing. The goal is to automate repetitive searching, price checking, and false-positive filtering so you spend less time watching the marketplace and more time deciding whether a candidate is actually worth contacting.

This repository contains only generic source code and example configuration. Local login state, personal watchlists, private config files, notification URLs, logs, screenshots, and monitoring results are intentionally ignored by Git.

## What It Does

- Opens a real browser with Playwright and reuses a user-managed login session.
- Searches one or more configured product keywords.
- Reads structured search API responses first, then falls back to DOM parsing.
- Filters candidates by `target_price`, `min_price`, `market_price`, required terms, and exclude terms.
- Rejects common false positives: deposits, accessories, repair parts, broken items, empty boxes, wanted posts, rentals, misleading low prices, and fake listing prices.
- Stores local deduplication state so the same listing does not alert repeatedly.
- Supports console output, macOS notifications, `ntfy`, generic webhooks, Bark, and ServerChan.

## Technical Stack

- **Python 3** for the monitor and runner scripts.
- **Playwright** for browser automation, login-state reuse, search-page loading, and API-response capture.
- **requests** for webhook, Bark, and ServerChan notifications.
- **Local JSON files** for config, browser state, deduplication state, and runtime output.

There is no database and no backend service. The project is easy to run on macOS, Linux, OpenClaw, a NAS container, or an agent workspace.

## Key Files

| File | Purpose |
| --- | --- |
| `goofish_monitor.py` | Core login, search, filtering, deduplication, and notification script |
| `run_watchlist.py` | Runs multiple local config files from a private watchlist |
| `push_serverchan.py` | Standalone ServerChan push helper |
| `config.example.json` | Safe example config without phone numbers, private product preferences, or tokens |
| `requirements.txt` | Python dependencies |
| `.gitignore` | Excludes local login state, private config, logs, and runtime output |

## Quick Start

```bash
git clone https://github.com/DouglaxYuan/goofish-monitor-lite.git
cd goofish-monitor-lite

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp config.example.json config.local.json
```

Edit `config.local.json`, then log in:

```bash
python goofish_monitor.py login --config config.local.json
```

Run a single monitor pass:

```bash
python goofish_monitor.py monitor --config config.local.json --once
```

Run continuously:

```bash
python goofish_monitor.py monitor --config config.local.json
```

## Required User Inputs

Required:

- `account.phone`: phone number used to help open the login flow. You may also leave it blank and log in manually.
- `products[].keyword`: search keyword.
- `products[].target_price`: highest price that should trigger an alert.
- `products[].min_price`: lower bound used to filter deposits, accessories, and misleading listings.
- `products[].required_any_terms`: at least one positive term should appear in listing text.

Recommended:

- `products[].market_price`: reference market price.
- `products[].exclude_terms`: product-specific exclude terms.
- `runtime.interval_seconds`: monitor interval.
- `runtime.jitter_seconds`: random delay between runs.

Optional notification fields:

- `notifications.ntfy_topic_url`
- `notifications.webhook_url`
- `notifications.bark_url`

ServerChan can read its key from an environment variable:

```bash
export SERVERCHAN_SENDKEY="SCTxxxxxxxx"
python push_serverchan.py "Title" "Markdown body"
```

Do not commit real phone numbers, notification URLs, SendKeys, browser state, or watchlists.

## Agent Quickstart

Give this to OpenClaw, Codex, Claude Code, or a smaller automation agent:

```text
This is a Python + Playwright Xianyu/Goofish price monitor. In the repo root, create a venv, install requirements.txt, and run `python -m playwright install chromium`. Copy `config.example.json` to `config.local.json`. Fill account.phone and products[].keyword, target_price, min_price, market_price, required_any_terms from the user's input. First run `python goofish_monitor.py login --config config.local.json` and let the user complete manual browser login. Then run `python goofish_monitor.py monitor --config config.local.json --once` for a test pass. If successful, run without `--once` for continuous monitoring. Never commit state/, data/, logs/, reports/, config.local.json, watchlist.json, user tokens, cookies, or notification URLs.
```

## Privacy And Safety

- The project does not bypass captchas or platform risk controls.
- It does not buy items automatically.
- Browser state stays in your local `state/` directory.
- Private configs, watchlists, logs, screenshots, and results are ignored by Git.
- The public repository only contains generic code and safe example config.

## License

MIT
