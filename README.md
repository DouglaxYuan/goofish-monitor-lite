# Goofish Monitor Lite

这是一个轻量版闲鱼/Goofish 捡漏监控脚本，参考了 `Usagi-org/ai-goofish-monitor` 的关键思路：Playwright 浏览器自动化、复用登录态、优先抓搜索接口 JSON、多层价格/关键词过滤、重复提醒去重、通知渠道解耦。

仓库只包含通用代码和示例配置；本地登录态、个人配置、watchlist、运行日志和监控结果不会提交到 Git。

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

脚本会打开可见浏览器并尝试填入配置里的手机号。你可以在浏览器里完成短信验证或扫码登录；脚本会持续保存登录截图到 `state/login.png`，登录成功后保存 cookies 到 `state/goofish_state.json`。

不会自动绕过验证码或风控。如果出现安全验证，需要人工在浏览器里处理，或者降低运行频率后重试。

## 监控

```bash
python goofish_monitor.py monitor --config config.example.json
python goofish_monitor.py monitor --config config.example.json --once
```

复制 `config.example.json` 为本地配置文件，然后修改 `products` 添加商品。建议每个商品配置：

- `keyword`: 闲鱼搜索词
- `target_price`: 触发提醒的最高价
- `min_price`: 过低价格阈值，用于过滤定金、配件、低价引流
- `market_price`: 参考市场价，用于计算折扣和识别异常低价
- `required_any_terms`: 标题/卖家/标签里至少命中一个的产品词
- `exclude_terms`: 该商品额外排除词

提醒数据会写到 `data/alerts.jsonl`，市场快照写到 `data/market_snapshots.jsonl`，已提醒去重写到 `data/seen_items.json`。

## 过滤策略

价格监控不能只看最低价，闲鱼上常见误报包括：定金、配件、包装盒、维修件、故障机、求购帖、租赁帖、低价引流、标价不是售价。这个脚本按顺序做过滤：

1. 价格必须在 `min_price` 和 `target_price` 之间。
2. 标题等文本必须命中 `required_any_terms`。
3. 命中全局或商品排除词则直接丢弃。
4. 低于 `market_price * very_low_price_ratio` 会扣分，避免“离谱低价”直接提醒。
5. 命中疑似引流词会扣分，最终分数低于 `default_min_score` 不提醒。

## 通知

默认会在控制台和 macOS 通知中心提醒。也可在 `notifications` 里配置：

- `ntfy_topic_url`
- `webhook_url`
- `bark_url`

## 迁移

把整个目录复制到 OpenClaw、服务器或其他智能体工作区即可。关键文件是：

- `goofish_monitor.py`
- `run_watchlist.py`
- `config.example.json`
- `requirements.txt`

如果迁移到新机器后登录态失效，重新运行 `login`。

## 给其他 agent 的最短说明

最短流程：

```bash
cd goofish-monitor-lite
python3 run_watchlist.py --once
```

本地运行时可以创建自己的 `watchlist.json` 和私有配置文件；这些运行态文件不会进入 Git。

## License

MIT
