#!/usr/bin/env python3
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, List

import requests
from bs4 import BeautifulSoup
from telegram import Bot

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WATCHLIST_FILE, STATE_FILE, POLL_INTERVAL


@dataclass
class WatchItem:
    site: str
    url: str


# def load_watchlist(path: str) -> List[WatchItem]:
#     items: List[WatchItem] = []
#     if not os.path.exists(path):
#         print(f"{path} not found - create with Markdown links [amazon url](amazon url)")
#         return items
#     with open(path) as f:
#         for line_num, line in enumerate(f, 1):
#             line = line.strip()
#             if not line or line.startswith("#"):
#                 continue
            
#             # Parse Markdown [text](url) format
#             m = re.search(r"\[.*?\]\((https://www\.amazon\.com/[^)]+)\)", line)
#             if m:
#                 url = m.group(1)
#                 items.append(WatchItem(site="amazon", url=url))
#                 continue
            
#             print(f"Invalid line {line_num}: {line}")
    
#     print(f"Loaded {len(items)} Amazon items from {path}")
#     return items

def load_watchlist(path: str) -> List[WatchItem]:
    items: List[WatchItem] = []
    if not os.path.exists(path):
        print(f"{path} not found")
        return items
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("http"):
                items.append(WatchItem(site="amazon", url=line))
    print(f"Loaded {len(items)} Amazon items")
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


def fetch_html(url: str) -> Optional[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
        print(f"HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None


def get_price_name_amazon(html: str) -> (str, Optional[float]):
    soup = BeautifulSoup(html, "html.parser")

    # Simple CAPTCHA / bot page detection
    text = soup.get_text(" ", strip=True)
    if "Enter the characters you see below" in text or "Type the characters you see in this image" in text:
        return "Amazon CAPTCHA / robot page", None

    title_el = soup.select_one("#productTitle") or soup.find("title")
    name = title_el.get_text(strip=True)[:80] if title_el else "Amazon Product"

    selectors = [
        "#corePrice_feature_div span.a-offscreen",
        ".a-price span.a-offscreen",
        "#price_inside_buybox",
        "#newBuyBoxPrice",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            p = parse_price(el.get_text())
            if p:
                return name, p

    # Fallback: scan full text
    p = parse_price(text)
    return name, p


async def check_item(item: WatchItem, state: Dict[str, float]) -> None:
    print(f"Checking {item.url}")
    html = fetch_html(item.url)
    if not html:
        print(f"❌ Fetch failed for {item.url}")
        return

    name, price = get_price_name_amazon(html)
    if price is None:
        # Track failures
        fails = state.get(f"{item.url}_fails", 0) + 1
        state[f"{item.url}_fails"] = fails
        if fails >= 3:
            msg = f"🚨 URL ISSUE\n*{item.url}*\nFailed {fails} polls\nCAPTCHA/404 likely"
            await send_telegram(msg)
            print(f"🚨 Alerted Telegram: {fails} fails for {item.url}")
        else:
            print(f"⚠️ Fail #{fails}/3 for {item.url}")
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
        print("No Amazon items in watchlist.")
        return

    state = load_state(STATE_FILE)
    print("🚀 Amazon-only Price Tracker (RPi, requests+BS4) started!")

    while True:
        for item in items:
            await check_item(item, state)
        save_state(STATE_FILE, state)
        print(f"⏳ Sleeping {POLL_INTERVAL // 60} minutes...")
        await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
