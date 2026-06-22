#!/usr/bin/env python3
"""
Portable Goofish/Xianyu deal monitor.

The script uses Playwright browser automation, keeps a reusable login state,
listens for Goofish search API responses first, and falls back to DOM parsing
when the API payload is not captured.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)


GOOFISH_HOME = "https://www.goofish.com/"
SEARCH_API_FRAGMENT = "/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/"
LOGIN_HOST_MARKERS = ("passport.goofish.com", "login.taobao.com", "mini_login")
LOGIN_SELECTORS = (
    "iframe#alibaba-login-box",
    "iframe[src*='passport.goofish.com']",
    "div[class*='login-modal']",
    "div[class*='login-modal-wrap']",
)
RISK_SELECTORS = (
    "div.baxia-dialog-mask",
    "div.J_MIDDLEWARE_FRAME_WIDGET",
    "iframe[src*='baxia']",
)


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{now_text()}] {message}", flush=True)


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Config/state JSON is invalid: {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def as_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = re.split(r"[\n,，]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw = list(value)
    else:
        raw = [value]
    terms: list[str] = []
    seen: set[str] = set()
    for item in raw:
        term = str(item).strip()
        key = term.lower()
        if term and key not in seen:
            seen.add(key)
            terms.append(term)
    return terms


def ascii_token_match(term: str, text: str) -> bool:
    normalized_term = normalize_text(term)
    normalized_text = normalize_text(text)
    if not normalized_term:
        return False
    if re.fullmatch(r"[a-z0-9 ./+-]+", normalized_term):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text


def any_term_matches(text: str, terms: list[str]) -> bool:
    return any(ascii_token_match(term, text) for term in terms)


CONDITION_NEGATION_MARKERS = ("无", "没", "没有", "未见", "不见", "不明显")
CONDITION_KEYWORDS = ("划痕", "划伤", "磕碰", "霉", "雾", "掉漆", "露白", "跑焦", "拆修")


def contextual_term_match(term: str, text: str) -> bool:
    normalized_term = normalize_text(term)
    normalized_text = normalize_text(text)
    if not normalized_term:
        return False
    if not any(keyword in normalized_term for keyword in CONDITION_KEYWORDS):
        return ascii_token_match(term, text)

    start = 0
    found = False
    while True:
        index = normalized_text.find(normalized_term, start)
        if index == -1:
            break
        found = True
        prefix = normalized_text[max(0, index - 8):index]
        if not any(marker in prefix for marker in CONDITION_NEGATION_MARKERS):
            return True
        start = index + len(normalized_term)
    return False if found else ascii_token_match(term, text)


def parse_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    text = str(value).strip().replace("¥", "").replace(",", "")
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(万)?", text)
    if not match:
        return None
    price = float(match.group(1))
    if match.group(2):
        price *= 10000
    return round(price, 2)


def safe_get(data: Any, *keys: Any, default: Any = None) -> Any:
    current = data
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list) and isinstance(key, int):
                current = current[key]
            else:
                return default
        except (KeyError, IndexError, TypeError):
            return default
    return current


def price_from_parts(parts: Any) -> str:
    if isinstance(parts, list):
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    else:
        text = str(parts or "")
    return text.replace("当前价", "").strip()


def item_key(item: dict[str, Any]) -> str:
    return str(item.get("item_id") or item.get("href") or f"{item.get('title')}|{item.get('price')}")


def mobile_goofish_link(link: str) -> str:
    if not link:
        return link
    return link.replace("fleamarket://", "https://www.goofish.com/")


@dataclass
class Candidate:
    product_name: str
    keyword: str
    title: str
    price: float
    href: str
    item_id: str
    seller: str
    area: str
    publish_time: str
    wants_count: Any
    tags: list[str]
    score: int
    reasons: list[str]
    raw: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {
            "time": datetime.now().isoformat(timespec="seconds"),
            "product": self.product_name,
            "keyword": self.keyword,
            "title": self.title,
            "price": self.price,
            "href": self.href,
            "item_id": self.item_id,
            "seller": self.seller,
            "area": self.area,
            "publish_time": self.publish_time,
            "wants_count": self.wants_count,
            "tags": self.tags,
            "score": self.score,
            "reasons": self.reasons,
        }


class GoofishMonitor:
    def __init__(self, config_path: Path):
        self.config_path = config_path.resolve()
        self.base_dir = self.config_path.parent
        self.config = read_json(self.config_path, {})
        if not self.config:
            raise SystemExit(f"Config is empty: {self.config_path}")

        account = self.config.get("account", {})
        self.storage_state = resolve_path(self.base_dir, account.get("storage_state", "state/goofish_state.json"))
        self.user_data_dir = resolve_path(self.base_dir, account.get("user_data_dir", "state/browser_profile"))
        self.login_screenshot = resolve_path(self.base_dir, account.get("login_screenshot", "state/login.png"))
        self.data_dir = resolve_path(self.base_dir, self.config.get("data_dir", "data"))
        self.seen_path = self.data_dir / "seen_items.json"
        self.alerts_path = self.data_dir / "alerts.jsonl"
        self.market_path = self.data_dir / "market_snapshots.jsonl"

        self.seen: dict[str, Any] = read_json(self.seen_path, {"items": {}})
        self.products = self.config.get("products") or []
        if not self.products:
            raise SystemExit("No products configured.")

    def context_options(self) -> dict[str, Any]:
        return {
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            "viewport": {"width": 1440, "height": 1100},
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        }

    def launch_options(self, *, force_headful: bool = False) -> dict[str, Any]:
        account = self.config.get("account", {})
        channel = str(account.get("browser_channel") or "").strip() or None
        launch_kwargs: dict[str, Any] = {
            "headless": False if force_headful else bool(account.get("headless", False)),
            "slow_mo": int(account.get("slow_mo_ms", 0) or 0),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel
        return launch_kwargs

    async def launch(self, playwright: Playwright, *, force_headful: bool = False) -> Browser:
        return await playwright.chromium.launch(**self.launch_options(force_headful=force_headful))

    async def new_persistent_context(self, playwright: Playwright, *, force_headful: bool = False) -> BrowserContext:
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        options = {k: v for k, v in self.context_options().items() if v is not None}
        options.update(self.launch_options(force_headful=force_headful))
        context = await playwright.chromium.launch_persistent_context(str(self.user_data_dir), **options)
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
            window.chrome = window.chrome || { runtime: {} };
            """
        )
        await self.seed_context_from_storage(context)
        return context

    async def seed_context_from_storage(self, context: BrowserContext) -> None:
        if not self.storage_state.exists():
            return
        state = read_json(self.storage_state, {})
        cookies = state.get("cookies") or []
        if cookies:
            try:
                await context.add_cookies(cookies)
            except Exception as exc:
                log(f"Unable to seed cookies from storage_state: {exc}")
        origins = state.get("origins") or []
        for origin in origins:
            origin_url = str(origin.get("origin") or "")
            local_storage = origin.get("localStorage") or []
            if not origin_url or not local_storage:
                continue
            page = await context.new_page()
            try:
                await page.goto(origin_url, wait_until="domcontentloaded", timeout=30000)
                await page.evaluate(
                    """entries => {
                        for (const entry of entries) {
                            if (entry && entry.name) localStorage.setItem(entry.name, entry.value || "");
                        }
                    }""",
                    local_storage,
                )
            except Exception:
                pass
            finally:
                await page.close()

    async def new_context(self, browser: Browser) -> BrowserContext:
        options = {k: v for k, v in self.context_options().items() if v is not None}
        if self.storage_state.exists():
            options["storage_state"] = str(self.storage_state)
        context = await browser.new_context(**options)
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] });
            window.chrome = window.chrome || { runtime: {} };
            """
        )
        return context

    async def login(self) -> None:
        async with async_playwright() as playwright:
            context = await self.new_persistent_context(playwright, force_headful=True)
            page = await context.new_page()
            await page.goto(GOOFISH_HOME, wait_until="domcontentloaded", timeout=60000)
            await self.try_fill_phone(page)
            await self.save_login_screenshot(page)
            log(f"Login page is open. Screenshot: {self.login_screenshot}")
            log("Complete SMS or QR login in the visible browser. Cookies will be saved after login is detected.")

            deadline = time.time() + 600
            while time.time() < deadline:
                if await self.is_logged_in(page):
                    self.storage_state.parent.mkdir(parents=True, exist_ok=True)
                    await context.storage_state(path=str(self.storage_state))
                    await self.save_login_screenshot(page)
                    log(f"Login detected. Storage state saved: {self.storage_state}")
                    await context.close()
                    return
                await self.try_fill_phone(page)
                await self.save_login_screenshot(page)
                await asyncio.sleep(5)

            await context.storage_state(path=str(self.storage_state))
            await context.close()
            log(f"Timed out waiting for login. Partial state saved: {self.storage_state}")

    async def try_fill_phone(self, page: Page) -> None:
        phone = str(self.config.get("account", {}).get("phone") or os.getenv("GOOFISH_PHONE") or "").strip()
        if not phone:
            return
        selectors = (
            "input[type='tel']",
            "input[placeholder*='手机']",
            "input[placeholder*='手机号']",
            "input[name*='phone']",
            "input[name*='mobile']",
        )
        for selector in selectors:
            try:
                field = page.locator(selector).first
                if await field.count() and await field.is_visible(timeout=1000):
                    current = await field.input_value()
                    if phone not in current:
                        await field.fill(phone)
                    return
            except Exception:
                continue

    async def save_login_screenshot(self, page: Page) -> None:
        try:
            self.login_screenshot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(self.login_screenshot), full_page=True)
        except Exception:
            pass

    async def is_logged_in(self, page: Page) -> bool:
        url = page.url.lower()
        if any(marker in url for marker in LOGIN_HOST_MARKERS):
            return False
        cookies = await page.context.cookies()
        cookie_names = {cookie.get("name", "") for cookie in cookies}
        strong_login_cookies = {
            "unb",
            "_nk_",
            "tracknick",
            "lgc",
            "sgcookie",
            "cookie17",
            "dnk",
            "sn",
            "uc1",
            "uc3",
        }
        if strong_login_cookies.intersection(cookie_names):
            try:
                await page.goto(GOOFISH_HOME, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            return True
        return False

    async def monitor_forever(self, *, once: bool = False, force_headful: bool = False) -> None:
        if not self.storage_state.exists() and not self.user_data_dir.exists():
            raise SystemExit(f"Login state not found. Run login first: {self.storage_state}")

        runtime = self.config.get("runtime", {})
        interval = int(runtime.get("interval_seconds", 300))
        jitter = int(runtime.get("jitter_seconds", 0))

        async with async_playwright() as playwright:
            context = await self.new_persistent_context(playwright, force_headful=force_headful)
            page = await context.new_page()
            try:
                while True:
                    started = time.time()
                    candidates = await self.run_round(page)
                    await self.notify_many(candidates)
                    await context.storage_state(path=str(self.storage_state))
                    if once:
                        break
                    wait_seconds = max(30, interval + random.randint(-jitter, jitter))
                    elapsed = int(time.time() - started)
                    log(f"Round finished in {elapsed}s. Sleeping {wait_seconds}s.")
                    await asyncio.sleep(wait_seconds)
            finally:
                write_json(self.seen_path, self.seen)
                await context.close()

    async def run_round(self, page: Page) -> list[Candidate]:
        log("Starting monitor round.")
        deals: list[Candidate] = []
        for product in self.products:
            product_deals = await self.check_product(page, product)
            deals.extend(product_deals)
            await self.human_delay()
        log(f"Round found {len(deals)} alert-worthy item(s).")
        return deals

    async def check_product(self, page: Page, product: dict[str, Any]) -> list[Candidate]:
        keyword = str(product.get("keyword") or product.get("name") or "").strip()
        if not keyword:
            return []

        runtime = self.config.get("runtime", {})
        max_pages = int(product.get("max_pages") or runtime.get("max_pages", 1))
        max_results = int(product.get("max_results") or runtime.get("max_results_per_product", 40))
        params = {"q": keyword}
        url = f"https://www.goofish.com/search?{urlencode(params)}"
        log(f"Searching: {keyword}")

        items: list[dict[str, Any]] = []
        try:
            await self.warm_home(page)
            response = await self.goto_and_capture_search(page, url)
            await self.assert_page_usable(page)
            if response:
                items.extend(await self.parse_search_response(response))
            if not items:
                items.extend(await self.extract_dom_items(page))
            for page_index in range(2, max_pages + 1):
                next_response = await self.next_page(page, page_index)
                if not next_response:
                    break
                items.extend(await self.parse_search_response(next_response))
                if len(items) >= max_results:
                    break
        except PlaywrightTimeoutError as exc:
            log(f"Timeout while searching {keyword}: {exc}")
        except RuntimeError as exc:
            log(str(exc))
            if self.config.get("runtime", {}).get("stop_on_risk_control", True):
                raise
        except Exception as exc:
            log(f"Search failed for {keyword}: {exc}")

        limited_items = items[:max_results]
        for item in limited_items:
            append_jsonl(self.market_path, {"time": datetime.now().isoformat(timespec="seconds"), "keyword": keyword, **item})

        candidates = [candidate for item in limited_items if (candidate := self.evaluate_item(item, product))]
        candidates.sort(key=lambda candidate: (candidate.price, -candidate.score))
        for candidate in candidates:
            log(f"Deal candidate: {candidate.product_name} ¥{candidate.price:g} score={candidate.score} {candidate.title[:50]}")
        return candidates

    async def warm_home(self, page: Page) -> None:
        try:
            await page.goto(GOOFISH_HOME, wait_until="domcontentloaded", timeout=20000)
            await page.mouse.wheel(0, random.randint(180, 520))
            await self.human_delay(0.8, 1.8)
        except Exception:
            pass

    async def goto_and_capture_search(self, page: Page, url: str) -> Response | None:
        timeout = int(self.config.get("runtime", {}).get("page_timeout_ms", 45000))
        try:
            async with page.expect_response(self.is_search_response, timeout=timeout) as response_info:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            response = await response_info.value
            if self.is_login_url(page.url):
                raise RuntimeError(f"Login required or state expired: {page.url}")
            return response
        except PlaywrightTimeoutError:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if self.is_login_url(page.url):
                raise RuntimeError(f"Login required or state expired: {page.url}")
            return None

    async def next_page(self, page: Page, page_index: int) -> Response | None:
        await self.assert_page_usable(page)
        selector = (
            "button[class*='search-pagination-arrow-container']"
            ":has([class*='search-pagination-arrow-right']):not([disabled])"
        )
        button = page.locator(selector).first
        try:
            if not await button.count():
                return None
            await button.scroll_into_view_if_needed()
            async with page.expect_response(self.is_search_response, timeout=20000) as response_info:
                await button.click(timeout=10000)
            await self.human_delay()
            return await response_info.value
        except Exception as exc:
            await self.assert_page_usable(page)
            log(f"Unable to advance to page {page_index}: {exc}")
            return None

    def is_search_response(self, response: Response) -> bool:
        return SEARCH_API_FRAGMENT in response.url and response.request.method.upper() == "POST"

    def is_login_url(self, url: str) -> bool:
        lowered = (url or "").lower()
        return any(marker in lowered for marker in LOGIN_HOST_MARKERS)

    async def assert_page_usable(self, page: Page) -> None:
        if self.is_login_url(page.url):
            raise RuntimeError(f"Login required or state expired: {page.url}")
        for selector in LOGIN_SELECTORS:
            try:
                if await page.locator(selector).first.is_visible(timeout=800):
                    screenshot = self.data_dir / f"login_required_{int(time.time())}.png"
                    await page.screenshot(path=str(screenshot), full_page=True)
                    raise RuntimeError(f"Login required or state expired. Screenshot: {screenshot}")
            except PlaywrightTimeoutError:
                continue
        for selector in RISK_SELECTORS:
            try:
                if await page.locator(selector).first.is_visible(timeout=1200):
                    screenshot = self.data_dir / f"risk_control_{int(time.time())}.png"
                    await page.screenshot(path=str(screenshot), full_page=True)
                    raise RuntimeError(f"Risk control detected ({selector}). Screenshot: {screenshot}")
            except PlaywrightTimeoutError:
                continue

    async def parse_search_response(self, response: Response) -> list[dict[str, Any]]:
        try:
            payload = await response.json()
        except Exception:
            return []
        result_list = safe_get(payload, "data", "resultList", default=[]) or []
        parsed: list[dict[str, Any]] = []
        for item in result_list:
            main = safe_get(item, "data", "item", "main", "exContent", default={}) or {}
            click_args = safe_get(item, "data", "item", "main", "clickParam", "args", default={}) or {}
            title = str(safe_get(main, "title", default="")).strip()
            price_text = price_from_parts(safe_get(main, "price", default=""))
            price = parse_price(price_text)
            if not title or price is None:
                continue
            publish_ms = str(click_args.get("publishTime") or "")
            publish_time = ""
            if publish_ms.isdigit():
                publish_time = datetime.fromtimestamp(int(publish_ms) / 1000).strftime("%Y-%m-%d %H:%M")
            tags = []
            if click_args.get("tag") == "freeship":
                tags.append("包邮")
            for tag_item in safe_get(main, "fishTags", "r1", "tagList", default=[]) or []:
                content = safe_get(tag_item, "data", "content", default="")
                if content:
                    tags.append(str(content))
            item_id = str(safe_get(main, "itemId", default="") or "")
            href = mobile_goofish_link(str(safe_get(main, "targetUrl", default="") or ""))
            if not href and item_id:
                href = f"https://www.goofish.com/item?id={item_id}"
            parsed.append(
                {
                    "title": title,
                    "price": price,
                    "price_text": price_text,
                    "href": href,
                    "item_id": item_id,
                    "seller": str(safe_get(main, "userNickName", default="") or ""),
                    "area": str(safe_get(main, "area", default="") or ""),
                    "publish_time": publish_time,
                    "wants_count": click_args.get("wantNum", ""),
                    "tags": tags,
                    "image_url": str(safe_get(main, "picUrl", default="") or ""),
                    "source": "api",
                }
            )
        log(f"Parsed {len(parsed)} item(s) from search API.")
        return parsed

    async def extract_dom_items(self, page: Page) -> list[dict[str, Any]]:
        expression = """
        () => {
          const cards = Array.from(document.querySelectorAll('a[class*="feeds-item-wrap"], [class*="feeds-item"]'));
          const results = [];
          for (const card of cards) {
            const titleEl = card.querySelector('[class*="main-title"], [class*="title"]');
            const priceEl = card.querySelector('[class*="number"], [class*="price"]');
            const linkEl = card.closest?.('a[href]') || card.querySelector?.('a[href]') || card;
            const title = (titleEl?.innerText || '').trim();
            const priceText = (priceEl?.innerText || '').trim();
            const href = linkEl?.href || '';
            if (title && priceText) results.push({ title, priceText, href });
          }
          return results;
        }
        """
        try:
            raw_items = await page.evaluate(expression)
        except Exception:
            return []
        parsed: list[dict[str, Any]] = []
        for raw in raw_items or []:
            price = parse_price(raw.get("priceText"))
            if price is None:
                continue
            href = raw.get("href") or ""
            item_id_match = re.search(r"id=(\d+)", href)
            parsed.append(
                {
                    "title": raw.get("title", ""),
                    "price": price,
                    "price_text": raw.get("priceText", ""),
                    "href": href,
                    "item_id": item_id_match.group(1) if item_id_match else "",
                    "seller": "",
                    "area": "",
                    "publish_time": "",
                    "wants_count": "",
                    "tags": [],
                    "image_url": "",
                    "source": "dom",
                }
            )
        log(f"Parsed {len(parsed)} item(s) from DOM fallback.")
        return parsed

    def evaluate_item(self, item: dict[str, Any], product: dict[str, Any]) -> Candidate | None:
        title = str(item.get("title") or "")
        text = " ".join([title, str(item.get("seller") or ""), str(item.get("area") or ""), " ".join(item.get("tags") or [])])
        price = parse_price(item.get("price"))
        if price is None:
            return None

        min_price = parse_price(product.get("min_price"))
        target_price = parse_price(product.get("target_price") or product.get("max_price"))
        market_price = parse_price(product.get("market_price"))
        if min_price is not None and price < min_price:
            return None
        if target_price is not None and price > target_price:
            return None

        required_terms = as_terms(product.get("required_any_terms") or product.get("product_terms"))
        if required_terms and not any_term_matches(text, required_terms):
            return None

        for group in product.get("required_term_groups") or []:
            group_terms = as_terms(group)
            if group_terms and not any_term_matches(text, group_terms):
                return None

        capacity_tb = parse_price(product.get("capacity_tb"))
        if capacity_tb is not None and not self.capacity_matches(text, int(capacity_tb)):
            return None

        global_excludes = as_terms(self.config.get("filters", {}).get("global_exclude_terms"))
        product_excludes = as_terms(product.get("exclude_terms"))
        matched_excludes = [term for term in global_excludes + product_excludes if ascii_token_match(term, text)]
        if matched_excludes:
            return None

        hard_excludes = as_terms(self.config.get("filters", {}).get("hard_exclude_terms"))
        matched_hard_excludes = [term for term in hard_excludes if contextual_term_match(term, text)]
        if matched_hard_excludes:
            return None

        score = 50
        reasons: list[str] = []
        if target_price is not None:
            discount = max(0.0, (target_price - price) / target_price)
            score += min(35, int(discount * 100))
            reasons.append(f"价格 ¥{price:g} <= 目标 ¥{target_price:g}")
        if market_price:
            market_discount = max(0.0, (market_price - price) / market_price)
            score += min(25, int(market_discount * 80))
            reasons.append(f"较参考价约低 {market_discount * 100:.1f}%")

        suspicious_terms = as_terms(self.config.get("filters", {}).get("suspicious_terms"))
        matched_suspicious = [term for term in suspicious_terms if contextual_term_match(term, text)]
        if matched_suspicious:
            score -= 35
            reasons.append("疑似低价陷阱: " + ", ".join(matched_suspicious[:4]))

        very_low_ratio = float(self.config.get("filters", {}).get("very_low_price_ratio", 0.35) or 0.35)
        if market_price and price < market_price * very_low_ratio:
            score -= 25
            reasons.append(f"价格低于参考价 {very_low_ratio:.0%}，需要人工复核")

        if "验货宝" in "".join(item.get("tags") or []):
            score += 5
            reasons.append("带验货宝标签")
        if "包邮" in "".join(item.get("tags") or []):
            score += 3
            reasons.append("包邮")

        positive_terms = as_terms(product.get("positive_terms") or self.config.get("filters", {}).get("positive_terms"))
        matched_positive = [term for term in positive_terms if ascii_token_match(term, text)]
        if matched_positive:
            score += min(12, len(matched_positive) * 4)
            reasons.append("成色: " + ", ".join(self.compact_terms(matched_positive)[:3]))

        min_score = int(product.get("min_score") or self.config.get("filters", {}).get("default_min_score", 60))
        if score < min_score:
            return None

        key = item_key(item)
        seen_items = self.seen.setdefault("items", {})
        if key in seen_items:
            return None
        seen_items[key] = {"first_seen": datetime.now().isoformat(timespec="seconds"), "title": title, "price": price}
        write_json(self.seen_path, self.seen)

        return Candidate(
            product_name=str(product.get("name") or product.get("keyword") or "未命名商品"),
            keyword=str(product.get("keyword") or ""),
            title=title,
            price=price,
            href=str(item.get("href") or ""),
            item_id=str(item.get("item_id") or ""),
            seller=str(item.get("seller") or ""),
            area=str(item.get("area") or ""),
            publish_time=str(item.get("publish_time") or ""),
            wants_count=item.get("wants_count", ""),
            tags=list(item.get("tags") or []),
            score=score,
            reasons=reasons,
            raw=item,
        )

    def capacity_matches(self, text: str, capacity_tb: int) -> bool:
        normalized = normalize_text(text)
        compact = re.sub(r"[\s_-]+", "", normalized)
        model_hints = [f"st{capacity_tb * 1000}nm"]
        model_hints.extend(
            {
                16: ["wuh721816"],
                18: ["wuh721818"],
                20: ["wuh722020"],
                22: ["wuh722222"],
                24: ["wuh722424"],
            }.get(capacity_tb, [])
        )
        if any(hint in compact for hint in model_hints):
            return True

        explicit_capacities = {
            int(match.group(1))
            for match in re.finditer(
                r"(?<!\d)(\d{1,2})\s*(?:t|tb)\b",
                text,
                flags=re.IGNORECASE,
            )
        }
        if explicit_capacities and capacity_tb not in explicit_capacities:
            return False
        return capacity_tb in explicit_capacities

    async def notify_many(self, candidates: list[Candidate]) -> None:
        for candidate in candidates:
            record = candidate.to_record()
            append_jsonl(self.alerts_path, record)

        if not candidates:
            return

        notifications = self.config.get("notifications", {})
        title, body = self.build_result_summary(candidates)

        if notifications.get("console", True):
            print("\n" + "=" * 72)
            print(title)
            print(body)
            print("=" * 72 + "\n")

        if notifications.get("mac_notification", False):
            self.mac_notify(title, body)
        if notifications.get("ntfy_topic_url"):
            await asyncio.to_thread(self.post_ntfy, notifications["ntfy_topic_url"], title, body)
        if notifications.get("webhook_url"):
            await asyncio.to_thread(self.post_webhook_many, notifications["webhook_url"], candidates)
        if notifications.get("bark_url"):
            await asyncio.to_thread(self.post_bark, notifications["bark_url"], title, body, candidates[0].href)
        cc_connect = notifications.get("cc_connect") or {}
        if cc_connect.get("enabled"):
            await asyncio.to_thread(self.post_cc_connect, cc_connect, title, body)

    def build_result_summary(self, candidates: list[Candidate]) -> tuple[str, str]:
        sorted_candidates = sorted(candidates, key=lambda candidate: (-candidate.score, candidate.price))
        total = len(sorted_candidates)
        title = f"闲鱼监控结果：发现 {total} 个候选"
        if self.is_lens_candidates(sorted_candidates):
            return title, self.build_lens_result_summary(sorted_candidates)
        lines = [f"本轮发现 {total} 个候选，按优先级列出："]
        for index, candidate in enumerate(sorted_candidates[:8], start=1):
            link = candidate.href or (f"https://www.goofish.com/item?id={candidate.item_id}" if candidate.item_id else "-")
            reasons = "；".join(candidate.reasons[:2]) or "价格命中"
            location = " / ".join(part for part in [candidate.area, candidate.seller] if part) or "-"
            lines.extend(
                [
                    "",
                    f"{index}. {candidate.product_name}  ¥{candidate.price:g}  评分 {candidate.score}",
                    f"   {candidate.title[:80]}",
                    f"   看点：{reasons}",
                    f"   地区/卖家：{location}",
                    f"   商品ID：{candidate.item_id or '-'}",
                    f"   链接：{link}",
                ]
            )
        if total > 8:
            lines.append(f"\n另有 {total - 8} 个候选未展开。")
        lines.append("\n复核重点：确认卖家信誉、商品状态、实拍凭证、售后条件和到手测试方式。")
        return title, "\n".join(lines)

    def is_lens_candidates(self, candidates: list[Candidate]) -> bool:
        return False

    def build_lens_result_summary(self, candidates: list[Candidate]) -> str:
        total = len(candidates)
        lines = [f"本轮发现 {total} 个镜头候选："]
        positive_terms = as_terms(self.config.get("filters", {}).get("positive_terms"))
        for index, candidate in enumerate(candidates[:8], start=1):
            link = candidate.href or (f"https://www.goofish.com/item?id={candidate.item_id}" if candidate.item_id else "-")
            text = " ".join([candidate.title, " ".join(candidate.reasons)])
            matched_condition = [term for term in positive_terms if ascii_token_match(term, text)]
            condition_terms = self.compact_terms(matched_condition)
            condition = "、".join(condition_terms[:3]) if condition_terms else "看标题成色"
            lines.extend(
                [
                    "",
                    f"{index}. {candidate.product_name}  ¥{candidate.price:g}",
                    f"   成色：{condition}",
                    f"   标题：{candidate.title[:70]}",
                    f"   链接：{link}",
                ]
            )
        if total > 8:
            lines.append(f"\n另有 {total - 8} 个候选未展开。")
        lines.append("\n复核重点：镜片无划痕、无霉雾，整体成色好。")
        return "\n".join(lines)

    def compact_terms(self, terms: list[str]) -> list[str]:
        compacted: list[str] = []
        for term in terms:
            normalized = normalize_text(term)
            if any(normalized != normalize_text(other) and normalized in normalize_text(other) for other in terms):
                continue
            if term not in compacted:
                compacted.append(term)
        return compacted

    def mac_notify(self, title: str, body: str) -> None:
        if sys.platform != "darwin" or not shutil.which("osascript"):
            return
        script = 'display notification %s with title %s' % (json.dumps(body[:220]), json.dumps(title))
        try:
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        except Exception:
            pass

    def post_ntfy(self, topic_url: str, title: str, body: str) -> None:
        response = requests.post(
            topic_url,
            data=body.encode("utf-8"),
            headers={"Title": title.encode("utf-8"), "Priority": "urgent", "Tags": "bell"},
            timeout=12,
        )
        response.raise_for_status()

    def post_webhook(self, webhook_url: str, candidate: Candidate) -> None:
        response = requests.post(webhook_url, json=candidate.to_record(), timeout=12)
        response.raise_for_status()

    def post_webhook_many(self, webhook_url: str, candidates: list[Candidate]) -> None:
        payload = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "type": "goofish_monitor_results",
            "count": len(candidates),
            "items": [candidate.to_record() for candidate in candidates],
        }
        response = requests.post(webhook_url, json=payload, timeout=12)
        response.raise_for_status()

    def post_bark(self, bark_url: str, title: str, body: str, href: str) -> None:
        response = requests.post(
            bark_url,
            json={"title": title, "body": body, "url": href, "level": "timeSensitive", "group": "闲鱼监控"},
            timeout=12,
        )
        response.raise_for_status()

    def post_cc_connect(self, config: dict[str, Any], title: str, body: str) -> None:
        command = str(config.get("command") or "cc-connect")
        project = str(config.get("project") or "").strip()
        session = str(config.get("session") or "").strip()
        timeout = int(config.get("timeout_seconds") or 30)
        message = f"## {title}\n\n{body}"
        args = [command, "send", "--stdin"]
        if project:
            args.extend(["--project", project])
        if session:
            args.extend(["--session", session])
        result = subprocess.run(
            args,
            input=message,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            error = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"cc-connect send failed: {error}")

    async def human_delay(self, min_seconds: float | None = None, max_seconds: float | None = None) -> None:
        runtime = self.config.get("runtime", {})
        low = float(min_seconds if min_seconds is not None else runtime.get("human_delay_min_seconds", 2.0))
        high = float(max_seconds if max_seconds is not None else runtime.get("human_delay_max_seconds", 5.0))
        await asyncio.sleep(random.uniform(low, max(low, high)))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Goofish/Xianyu browser monitor")
    parser.add_argument("command", choices=["login", "monitor"], help="login saves browser state; monitor searches products")
    parser.add_argument("--config", default="config.example.json", help="Path to JSON config")
    parser.add_argument("--once", action="store_true", help="Run one monitor round and exit")
    parser.add_argument("--headful", action="store_true", help="Run monitor with a visible browser for debugging.")
    return parser.parse_args()


async def async_main() -> None:
    args = parse_args()
    monitor = GoofishMonitor(Path(args.config))
    if args.command == "login":
        await monitor.login()
    elif args.command == "monitor":
        await monitor.monitor_forever(once=args.once, force_headful=args.headful)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        log("Interrupted.")


if __name__ == "__main__":
    main()
