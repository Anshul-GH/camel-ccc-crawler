#!/usr/bin/env python3

import re
import time
import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

import camel3.constants as const


@dataclass
class WatchItem:
    site: str
    url: str


# ---------- Config & State ----------

def load_watchlist(path: str) -> List[WatchItem]:
    items: List[WatchItem] = []
    if not os.path.exists(path):
        print(f"⚠️ {path} not found")
        return items

    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                print(f"⚠️ Invalid line {line_num}: {line}")
                continue
            site, url = parts[0].lower(), parts[1]
            items.append(WatchItem(site=site, url=url))
    print(f"📄 Loaded {len(items)} watch items from {path}")
    return items


def load_state(path: str) -> Dict[str, float]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ Failed to load state {path}: {e}")
            return {}
    return {}


def save_state(path: str, state: Dict[str, float]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


# ---------- Telegram ----------

def send_telegram(text: str) -> None:
    api_url = f"https://api.telegram.org/bot{const.PT_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            api_url,
            data={"chat_id": const.PT_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.status_code == 200:
            print("✅ Telegram sent")
        else:
            print(f"❌ Telegram error {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")


# ---------- Fetch & helpers ----------

def parse_price(text: str) -> Optional[float]:
    m = re.search(r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def fetch_html(url: str) -> Optional[str]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Mac Safari/605.1.15)"},
            timeout=45,
        )
        if resp.status_code == 200:
            return resp.text
        print(f"⚠️ HTTP {resp.status_code}: {url}")
        return None
    except Exception as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return None


# ---------- Site-specific price/name ----------

def get_price_amazon(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "#corePriceDisplay_desktop_feature_div span.a-offscreen",
        "span.a-price span.a-offscreen",
        ".a-price[data-a-size='xl'] span.a-offscreen",
        ".a-price[data-a-size='m'] span.a-offscreen",
        ".a-price-whole + .a-price-fraction",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            p = parse_price(el.get_text())
            if p is not None:
                return p
    # Gift card / non‑standard pages may not match. [web:160]
    return None


def get_name_amazon(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("#productTitle")
    if title:
        return title.get_text(strip=True)[:80]
    t = soup.find("title")
    return t.get_text(strip=True)[:80] if t else "Amazon Product"


def get_price_bestbuy(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "[data-testid='priceView-hero-price'] span",
        ".priceView-hero-price span",
        ".pricing-price__regular-price",
        ".price-block__primary-price",
    ]
    for sel in selectors:
        for el in soup.select(sel):
            p = parse_price(el.get_text())
            if p is not None:
                return p
    return None  # Best Buy often needs JS / headless. [web:161][web:165]


def get_name_bestbuy(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:80]
    t = soup.find("title")
    return t.get_text(strip=True)[:80] if t else "Best Buy Product"


def get_price_walmart(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Robot or human" in text:
        print("  ⚠️ Walmart: Robot/CAPTCHA page, cannot parse with requests")
        return None  # Needs headless browser/proxy. [web:199][web:203]

    selectors = [
        "[data-automation-id='product-price']",
        ".w-price--current",
        ".price-group .price",
        ".prod-PriceToPay span",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            p = parse_price(el.get_text())
            if p is not None:
                return p
    return parse_price(text)


def get_name_walmart(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:80]
    t = soup.find("title")
    return t.get_text(strip=True)[:80] if t else "Walmart Product"


def get_price_metro(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for label_text in ["Full price", "Retail price", "List price", "One-time payment"]:
        for label in soup.find_all(string=re.compile(label_text, re.I)):
            parent = label.parent
            segment = parent.get_text(" ", strip=True)
            p = parse_price(segment)
            if p:
                candidates.append(p)

    if candidates:
        return max(candidates)

    all_text = soup.get_text("\n", strip=True)
    prices = []
    for ln in all_text.splitlines():
        low = ln.lower()
        if "$" not in ln:
            continue
        if "/mo" in low or "per month" in low:
            continue
        p = parse_price(ln)
        if p:
            prices.append(p)
    if prices:
        return max(prices)
    return None


def get_name_metro(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:80]
    t = soup.find("title")
    return t.get_text(strip=True)[:80] if t else "Metro Product"


def get_price_straighttalk(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        ".product-price",
        "[id*='price']",
    ]
    candidates = []
    for sel in selectors:
        for el in soup.select(sel):
            txt = el.get_text(" ", strip=True)
            low = txt.lower()
            if "/mo" in low or "per month" in low:
                continue
            p = parse_price(txt)
            if p:
                candidates.append(p)
    if candidates:
        return max(candidates)

    all_text = soup.get_text("\n", strip=True)
    prices = []
    for ln in all_text.splitlines():
        low = ln.lower()
        if "$" not in ln:
            continue
        if "/mo" in low or "per month" in low:
            continue
        p = parse_price(ln)
        if p:
            prices.append(p)
    if prices:
        return max(prices)
    return None


def get_name_straighttalk(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:80]
    t = soup.find("title")
    return t.get_text(strip=True)[:80] if t else "Straight Talk Product"


def get_name_generic(html: str, site: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)[:80]
    t = soup.find("title")
    if t:
        return t.get_text(strip=True)[:80]
    return f"{site.title()} Product"


def get_price_generic(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")
    return parse_price(soup.get_text())


def get_name_and_price(item: WatchItem) -> Tuple[str, Optional[float]]:
    html = fetch_html(item.url)
    if not html:
        return "Fetch failed", None

    print(f"  📄 Page size: {len(html)//1000}KB")
    site = item.site

    if site == "amazon":
        return get_name_amazon(html), get_price_amazon(html)
    if site == "bestbuy":
        return get_name_bestbuy(html), get_price_bestbuy(html)
    if site == "walmart":
        return get_name_walmart(html), get_price_walmart(html)
    if site == "metro":
        return get_name_metro(html), get_price_metro(html)
    if site == "straighttalk":
        return get_name_straighttalk(html), get_price_straighttalk(html)

    name = get_name_generic(html, site)
    price = get_price_generic(html)
    return name, price


# ---------- Main loop ----------

def main():
    print("🚀 PRICE DROP ALERT POLLER\n")
    watch_items = load_watchlist(const.WATCHLIST_FILE)
    if not watch_items:
        print("⚠️ No watch items. Edit pt_watchlist.txt and restart.")
        return

    state = load_state(const.STATE_FILE)
    print(f"📊 Loaded state for {len(state)} URLs\n")

    while True:
        for item in watch_items:
            print(f"🔎 Checking {item.site} | {item.url}")
            name, price = get_name_and_price(item)

            if price is None:
                print(f"  ⚠️ Could not find price for: {name}")
                continue

            key = item.url
            last_price = state.get(key)

            if last_price is None:
                state[key] = price
                print(f"  📌 Initial price set: {price:.2f}")
                save_state(const.STATE_FILE, state)
                continue

            if price != last_price:
                direction = "dropped" if price < last_price else "increased"
                diff = abs(last_price - price)
                pct = (diff / last_price) * 100 if last_price > 0 else 0.0
                msg = (
                    f"🛎 *Price {direction}!*\n"
                    f"*{name}*\n"
                    f"{item.url}\n"
                    f"Old: ${last_price:.2f}\n"
                    f"New: ${price:.2f}\n"
                    f"Change: ${diff:.2f} ({pct:.1f}%)"
                )
                print(f"  🔁 Price {direction}: {last_price:.2f} → {price:.2f}")
                send_telegram(msg)
                state[key] = price
                save_state(const.STATE_FILE, state)
            else:
                print(f"  ✅ No change. Current: {price:.2f}")

            time.sleep(2)

        print(f"\n⏳ Sleeping {const.POLL_INTERVAL}s...\n")
        time.sleep(const.POLL_INTERVAL)


if __name__ == "__main__":
    main()
