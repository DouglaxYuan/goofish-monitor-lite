# Agent 快速启动 / Agent Quickstart

## 中文

这是一个 Python + Playwright 的闲鱼 / Goofish 价格监控项目。适合让 OpenClaw、Codex、Claude Code 或小模型 agent 快速接手运行。

### 最小步骤

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp config.example.json config.local.json
```

请让用户提供：

- 闲鱼登录手机号，填入 `account.phone`，也可以留空让用户手动登录。
- 商品搜索词，填入 `products[].keyword`。
- 目标提醒价，填入 `products[].target_price`。
- 最低有效价，填入 `products[].min_price`。
- 参考市场价，填入 `products[].market_price`。
- 必须命中的商品词，填入 `products[].required_any_terms`。
- 需要排除的词，填入 `products[].exclude_terms`。

首次登录：

```bash
python goofish_monitor.py login --config config.local.json
```

让用户在可见浏览器里完成短信、扫码或人工验证。不要尝试绕过验证码或风控。

单次测试：

```bash
python goofish_monitor.py monitor --config config.local.json --once
```

持续运行：

```bash
python goofish_monitor.py monitor --config config.local.json
```

### 不要提交或输出

- `state/`
- `data/`
- `logs/`
- `reports/`
- `config.local.json`
- `watchlist.json`
- cookie、token、通知 URL、Server 酱 SendKey

## English

This is a Python + Playwright price monitor for Xianyu / Goofish. It is suitable for OpenClaw, Codex, Claude Code, or smaller agents that need a direct operational checklist.

### Minimal Steps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp config.example.json config.local.json
```

Ask the user for:

- Login phone number, written to `account.phone`, or leave it blank for manual login.
- Product search keyword, written to `products[].keyword`.
- Alert target price, written to `products[].target_price`.
- Minimum valid price, written to `products[].min_price`.
- Reference market price, written to `products[].market_price`.
- Required positive terms, written to `products[].required_any_terms`.
- Exclude terms, written to `products[].exclude_terms`.

First login:

```bash
python goofish_monitor.py login --config config.local.json
```

Let the user complete SMS, QR, or manual verification in the visible browser. Do not bypass captchas or risk controls.

Single test run:

```bash
python goofish_monitor.py monitor --config config.local.json --once
```

Continuous run:

```bash
python goofish_monitor.py monitor --config config.local.json
```

### Never Commit Or Print

- `state/`
- `data/`
- `logs/`
- `reports/`
- `config.local.json`
- `watchlist.json`
- cookies, tokens, notification URLs, ServerChan SendKey
