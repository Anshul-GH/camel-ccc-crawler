#!/usr/bin/env python3
import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Optional, Dict

from playwright.async_api import async_playwright
from telegram import Bot
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WATCHLIST_FILE, STATE_FILE, POLL_INTERVAL


@dataclass
class WatchItem:
    site: str
    url: str


def load_watchlist(path: str) -> list[WatchItem]:
    items: list[WatchItem] = []
    if not os.path.exists(path):
        print(f"{path} not found - create with 'site https://url'")
        return items
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = re.split(r'\s+', line, maxsplit=1)
            if len(parts) < 2:
                print(f"Invalid line {line_num}: {line}")
                continue
            site, url = parts[0].lower(), parts[1]
            items.append(WatchItem(site=site, url=url))
    print(f"Loaded {len(items)} watch items from {path}")
    return items


def load_state(path: str) -> Dict[str, float]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load state {path}: {e}")
    return {}


def save_state(path: str, state: Dict[str, float]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


async def send_telegram(msg: str) -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="Markdown")


def parse_price(text: str) -> Optional[float]:
    m = re.search(r"[\$£€]?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)", text)
    return float(m.group(1).replace(",", "")) if m else None


async def get_price_name(item: WatchItem) -> tuple[str, Optional[float]]:
    """Open page with Playwright, return (name, price) or (name, None)."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,  # headless for RPi
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-background-timer-throttling",
                "--single-process",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Heavier timeout for JS-heavy sites
        try:
            if item.site in ("bestbuy", "walmart"):
                await page.goto(item.url, wait_until="networkidle", timeout=90000)
            else:
                await page.goto(item.url, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"Timeout/err loading {item.url}: {e}")
            await browser.close()
            return item.url[:80], None

        await page.wait_for_timeout(4000)

        title = (await page.title()) or f"{item.site.title()} Product"
        name = title[:80]

        # Robot check for Walmart etc.
        text_sample = (await page.text_content("body")) or ""
        if "robot" in text_sample.lower() and "human" in text_sample.lower():
            print(f"⚠️ Robot check page for {item.site}, skipping price.")
            await browser.close()
            return name, None

        # Site-specific selectors
        selectors: dict[str, str] = {
            "amazon": ".a-price span.a-offscreen, .a-price-whole",
            "bestbuy": "[data-testid='priceView-hero-price'], .priceView-hero-price",
            "walmart": "[data-automation-id='product-price'], .w-price--current, .price",
        }
        selector = selectors.get(item.site, "text=/\\$/")

        price: Optional[float] = None

        # Primary selector
        try:
            el = await page.wait_for_selector(selector, timeout=8000)
            txt = await el.inner_text()
            price = parse_price(txt)
        except Exception:
            pass

        # Fallback: scan whole HTML
        if price is None:
            try:
                html = await page.content()
                price = parse_price(html)
            except Exception:
                price = None

        await browser.close()
        # Filter out invalid zero prices
        if price == 0:
            price = None
        return name, price


async def check_item(item: WatchItem, state: Dict[str, float]) -> None:
    print(f"Checking {item.site}: {item.url}")
    name, price = await get_price_name(item)
    if price is None:
        print(f"❌ Could not find valid price for {name}")
        return

    key = item.url
    last = state.get(key)

    if last is None:
        state[key] = price
        print(f"✅ Initial: ${price:.2f} - {name}")
        return

    if abs(price - last) > 0.01:
        direction = "🟢 DROPPED" if price < last else "🔴 INCREASED"
        diff = abs(last - price)
        pct = (diff / last) * 100 if last != 0 else 0.0
        msg = (
            f"{direction}\n"
            f"*{name}*\n"
            f"{item.url}\n"
            f"Old: ${last:.2f} → New: ${price:.2f}\n"
            f"Δ ${diff:.2f} ({pct:.1f}%)"
        )
        await send_telegram(msg)
        print(f"🚨 ALERT {direction}: ${last:.2f} → ${price:.2f} ({name})")
    else:
        print(f"➡️  Stable: ${price:.2f} ({name})")

    state[key] = price


async def main() -> None:
    items = load_watchlist(WATCHLIST_FILE)
    if not items:
        print("No watch items. Add lines like: amazon https://www.amazon.com/dp/...")
        return

    state = load_state(STATE_FILE)
    print("🚀 Playwright Price Tracker (RPi ARM64) started!")

    while True:
        for item in items:
            await check_item(item, state)
        save_state(STATE_FILE, state)
        print(f"⏳ Sleeping {POLL_INTERVAL // 60} min...")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
