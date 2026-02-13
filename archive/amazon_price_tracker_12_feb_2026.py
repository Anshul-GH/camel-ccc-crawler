#!/usr/bin/env python3
import random
import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from config import (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, WATCHLIST_FILE, 
                   STATE_FILE, POLL_INTERVAL, VALID_SELLERS_FILE)
import logging
from logging.handlers import RotatingFileHandler

@dataclass
class WatchItem:
    site: str
    url: str

# Logging setup
log_handler = RotatingFileHandler('amazon_tracker.log', maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)
logger = logging.getLogger('AmazonTracker')

def load_watchlist(path: str) -> List[WatchItem]:
    items = []
    if not os.path.exists(path):
        logger.info(f"{path} not found")
        return items
    with open(path) as f:
        for linenum, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'): continue
            if line.startswith('http'):
                url = line
            else:
                asin = line
                if not (asin.startswith('B') and len(asin) == 10):
                    logger.info(f"Invalid ASIN on line {linenum}: {line}")
                    continue
                url = f"https://www.amazon.com/dp/{asin}"
            items.append(WatchItem(site='amazon', url=url))
    logger.info(f"Loaded {len(items)} Amazon items")
    return items

def load_state(path: str) -> Dict[str, float]:
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.info(f"Failed to load state {path}: {e}")
    return {}

def save_state(path: str, state: Dict[str, float]) -> None:
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)

async def send_telegram(msg: str) -> None:
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode='Markdown')

def parse_price_text(text: str) -> Optional[float]:
    m = re.search(r'[\d]{1,3}(?:,[\d]{3})*\.[\d]{2}', text)
    if m:
        # Capture the full matched price string, not group(1)
        price_str = m.group(0).replace(',', '').replace('$', '')
        return float(price_str)
    return None

def load_valid_sellers(sellers_file: str) -> set[str]:
    if not os.path.exists(sellers_file):
        logger.warning(f"{sellers_file} not found, using defaults")
        return {"amazon.com", "amazon resale", "amazon warehouse deals"}
    sellers = set()
    with open(sellers_file, 'r') as f:
        for line in f:
            seller = line.strip()
            if seller:
                sellers.add(seller.lower())
    logger.info(f"Loaded {len(sellers)} valid sellers")
    return sellers

def fetch_html(url: str, retry_count: int = 0) -> Optional[str]:
    if retry_count > 0:
        delay = 2 ** retry_count + random.uniform(1, 3)
        logger.info(f"Backoff {retry_count}/3: {delay:.1f}s")
        time.sleep(delay)
    
    # 🔥 ROTATING USER AGENTS (3 browsers)
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    # 🔥 FULL BROWSER HEADERS (anti-bot)
    headers = {
        'User-Agent': random.choice(user_agents),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    # 🔥 PROXY SUPPORT (uncomment + add your proxy)
    # proxies = None
    # proxies = {
    #     'http': 'http://username:password@proxy-ip:port',
    #     'https': 'http://username:password@proxy-ip:port'
    # }
    # Or FREE proxy: 
    proxies = {'http': 'http://20.210.30.148:80', 'https': 'http://20.210.30.148:80'}
    
    try:
        resp = requests.get(
            url, 
            headers=headers, 
            proxies=proxies,
            timeout=25,
            allow_redirects=True
        )
        resp.raise_for_status()
        
        # CAPTCHA/BOT check
        if "captcha" in resp.text.lower() or "robot" in resp.text.lower():
            logger.warning(f"CAPTCHA detected: {url}")
            if retry_count < 3:
                return fetch_html(url, retry_count + 1)
            return None
            
        return resp.text
        
    except requests.exceptions.RequestException as e:
        logger.warning(f"Fetch fail {retry_count+1}/3 {url}: {str(e)[:50]}")
        if retry_count < 3:
            return fetch_html(url, retry_count + 1)
        
        logger.error(f"Max retries exceeded: {url}")
        return None

def get_price_name_amazon(html: str, valid_sellers: set[str]) -> tuple[str, Optional[float]]:
    """Return (product_name, price_from_buybox_valid_seller_or_None)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # CAPTCHA check
    if "Enter the characters you see below" in text or "Type the characters you see in this image" in text:
        return "Amazon CAPTCHA/robot page", None

    # Product title
    title_el = soup.select_one("#productTitle") or soup.find("title")
    name = title_el.get_text(strip=True)[:80] if title_el else "Amazon Product"
    if name == "Amazon.com" or (len(name) < 20 and "Amazon" in name):
        return name, None

    # Find seller FIRST
    buybox_seller_selectors = [
        "#sellerProfileTriggerId",
        "#merchant-info a", 
        ".sellerName",
    ]
    
    seller_text = None
    for sel in buybox_seller_selectors:
        el = soup.select_one(sel)
        if el:
            seller_text = el.get_text(" ", strip=True).lower()
            break
    
    seller_match = None
    if seller_text:
        for valid in valid_sellers:
            if valid in seller_text:
                seller_match = valid
                break

    if seller_match:
        logger.debug(f"Seller '{seller_match}' found in: {seller_text[:100]}")
        
        # PRIORITY 1: Amazon Resale Deal Prices (ACTUAL PAY PRICE)
        priority_prices = [
            "#priceblock_dealprice",
            "#priceblock_dealprice span.a-offscreen",
            "#priceblock_ourprice", 
            "#priceblock_ourprice span.a-offscreen",
            ".a-price.a-text-price.a-size-medium span.a-offscreen",
            "#apexOfferPriceBlock span.a-offscreen",
        ]

        # PRIORITY 2: Buybox prices (list price fallback)
        buybox_prices = [
            "#price_inside_buybox span.a-offscreen",
            ".buybox-price span.a-offscreen",
            "#corePrice_feature_div span.a-offscreen",  # ← This was grabbing $899!
        ]

        # PRIORITY 3: Last resort fallback
        fallback_prices = [
            "#priceblock span.a-offscreen",
            "#priceblock_shippingmessage",
        ]

        # Try in priority order - DEAL PRICES FIRST!
        for selector_list, priority in [(priority_prices, "deal"), (buybox_prices, "buybox"), (fallback_prices, "fallback")]:
            for sel in selector_list:
                el = soup.select_one(sel)
                if el:
                    price_text = el.get_text()
                    price = parse_price_text(price_text)
                    if price and 0.01 <= price <= 5000:
                        logger.info(f"Buybox match ${price:.2f} from {seller_match} for {name} [SEL:{sel}] [{priority}]")
                        return name, price
                    else:
                        logger.debug(f"Price rejected from {sel}: '{price_text[:50]}' -> {price}")

    logger.debug(f"No valid buybox price for {name} (seller: {seller_match})")
    return name, None

async def check_item(item: WatchItem, state: Dict[str, float], valid_sellers: set[str]) -> None:
    cooldown_key = f"{item.url}:cooldown_until"
    cooldown_until = state.get(cooldown_key)
    if cooldown_until and datetime.now().timestamp() < cooldown_until:
        logger.info(f"Cooldown: {item.url}")
        return

    logger.info(f"Checking {item.url}")
    await asyncio.sleep(random.uniform(2, 6))

    # Extract ASIN from URL
    asin_match = re.search(r'/dp/([A-Z0-9]{10})', item.url)
    if not asin_match:
        logger.warning(f"Cannot extract ASIN from {item.url}")
        return
    asin = asin_match.group(1)

    # 🔥 NUCLEAR OPTION: OFFERS PAGE FIRST (Amazon Resale lives here!)
    offers_url = f"https://www.amazon.com/gp/offer-listing/{asin}"
    offers_html = fetch_html(offers_url)
    name, offers_price = None, None
    if offers_html:
        logger.debug(f"Checking offers page for {asin}")
        name, offers_price = get_price_name_offers(offers_html, valid_sellers)

    # Buybox as BACKUP only
    buybox_price = None
    html = fetch_html(item.url)
    if html:
        _, buybox_price = get_price_name_amazon(html, valid_sellers)

    # ALWAYS use LOWEST price from valid sellers (offers page usually wins)
    price = None
    price_source = ""
    if offers_price and offers_price > 0:
        price = offers_price
        price_source = "offers"
    if buybox_price and (price is None or buybox_price < price):
        price = buybox_price
        price_source = "buybox"

    if price is None:
        fails_key = f"{item.url}:fails"
        fails = state.get(fails_key, 0) + 1
        state[fails_key] = fails
        if fails >= 6:
            msg = f"🚨 URL ISSUE: {item.url} ({fails} polls/404)"
            await send_telegram(msg)
            logger.error(f"ISSUE: {item.url} ({fails})")
            state[cooldown_key] = datetime.now().timestamp() + timedelta(hours=24).total_seconds()
        else:
            logger.warning(f"Fail {fails}/6: {item.url}")
        return

    # Reset fail counter on success
    fails_key = f"{item.url}:fails"
    if fails_key in state:
        del state[fails_key]

    key = item.url
    last = state.get(key)
    if last is None:
        state[key] = price
        logger.info(f"Initial price ${price:.2f} ({price_source}) - {name[:60]}")
        return

    if abs(price - last) >= 0.01:
        direction = "🟢 DROPPED" if price < last else "🔴 INCREASED"
        diff = abs(last - price)
        pct = diff / last * 100 if last != 0 else 0.0
        msg = f"{direction}\n{name[:80]}\n{item.url}\n*Old:* ${last:.2f} → *New:* ${price:.2f}\n*{diff:.2f}* ({pct:.1f}%)"
        await send_telegram(msg)
        logger.info(f"{direction} ${last:.2f}→${price:.2f} ({price_source}) {name[:40]}")
    else:
        logger.info(f"Stable price ${price:.2f} ({price_source}) {name[:40]}")
    
    state[key] = price


def get_price_name_offers(html: str, valid_sellers: set[str]) -> tuple[str, Optional[float]]:
    """Scan Amazon OFFICIAL offers page - ALL sellers for main product only."""
    soup = BeautifulSoup(html, "html.parser")
    
    best_price = float('inf')
    best_seller = None
    
    # Amazon's OFFICIAL offer containers (NO ads here)
    offer_containers = soup.select(".olpOffer, .a-row.olpOffer, #olpOfferList")
    
    for container in offer_containers[:15]:  # Top 15 offers only
        seller_el = container.select_one(".olpSellerName a, .olpSellerName, h3, .seller-name")
        if not seller_el:
            continue
            
        seller_text = seller_el.get_text(" ", strip=True).lower()
        seller_match = None
        for valid in valid_sellers:
            if valid in seller_text:
                seller_match = valid
                break
        if not seller_match:
            continue
            
        price_el = container.select_one(".olpOfferPrice, .a-price-whole, .a-offscreen, .offer-price")
        if not price_el:
            continue
            
        price = parse_price_text(price_el.get_text())
        if price and 0.01 <= price <= 5000 and price < best_price:
            best_price = price
            best_seller = seller_match
    
    if best_price != float('inf'):
        logger.info(f"Offers: Lowest ${best_price:.2f} from {best_seller}")
        return "Main product (offers)", best_price
    
    logger.debug("No valid offers found")
    return "Main product (no offers)", None

async def main() -> None:
    items = load_watchlist(WATCHLIST_FILE)
    if not items:
        logger.info("No Amazon items in watchlist.")
        return
    
    valid_sellers = load_valid_sellers(VALID_SELLERS_FILE)
    state = load_state(STATE_FILE)
    
    logger.info("🚀 Amazon Tracker - 3x/DAY (6hr+ apart) STARTED!")
    
    while True:
        now = datetime.now()
        hour = now.hour
        
        # Generate 3 random times with MINIMUM 6hr spacing
        times = []
        first = random.randint(0, 5)   # 00:00-05:59
        times.append(first)
        second = first + random.randint(6, 9)  # 6-9hr later
        if second > 23: second -= 24
        times.append(second)
        third = second + random.randint(6, 9)  # Another 6-9hr
        if third > 23: third -= 24
        times.append(third)
        
        # Sort chronologically (handles overnight)
        poll_times = sorted(times)
        
        # Find next poll time
        next_poll_hour = None
        for p_hour in poll_times:
            if hour < p_hour:
                next_poll_hour = p_hour
                break
        
        if next_poll_hour is None:
            next_poll_hour = poll_times[0] + 24  # Tomorrow
        
        # Sleep until next poll (+/- 30min jitter)
        sleep_hours = next_poll_hour - hour
        jitter_minutes = random.randint(-30, 30)
        sleep_seconds = (sleep_hours * 3600) + (jitter_minutes * 60)
        
        logger.info(f"⏰ Next poll: {next_poll_hour:02d}:00 (in {sleep_hours:.1f}hr) - 6hr spacing")
        logger.info(f"📅 Today: {', '.join(f'{h:02d}:00' for h in poll_times)}")
        
        await asyncio.sleep(max(0, sleep_seconds))  # No negative sleep
        
        # 🔥 FULL CYCLE EXECUTION
        logger.info(f"🕐 POLLING NOW {datetime.now().strftime('%H:%M:%S')} - {len(items)} items")
        shuffled_items = items.copy()
        random.shuffle(shuffled_items)
        
        for i, item in enumerate(shuffled_items):
            logger.info(f"Progress: {(i+1)/len(items)*100:.0f}%")
            await check_item(item, state, valid_sellers)
            if i < len(items) - 1:
                await asyncio.sleep(random.uniform(4, 10))
        
        # Summary
        active_items = len([k for k in state if not k.endswith((':fails', ':cooldown'))])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        summary_msg = f"✅ 3x/DAY (6hr): {active_items}/{len(items)} @ {timestamp}"
        await send_telegram(summary_msg)
        save_state(STATE_FILE, state)

if __name__ == "__main__":
    asyncio.run(main())
