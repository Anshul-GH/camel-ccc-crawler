#!/usr/bin/env python3

import re
import time
import os
import subprocess
from datetime import datetime
from collections import OrderedDict
import camel3.constants as const

import requests
from bs4 import BeautifulSoup


def is_valid_asin(asin):
    return bool(re.match(r'^B[A-Z0-9]{9}$', asin))


def get_html():
    cmd = ['curl', '-s', '-L', '-A', 'Mozilla/5.0 Mac Safari/605.1.15', '--compressed', const.URL]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.stdout.decode(errors='ignore')
    except Exception:
        return ''


def parse_deals(html):
    """
    1) Find ASINs from /product/ links (old logic)
    2) Fallback to amazon.com/dp links if needed
    3) Always produce up to 5 deals (no skips)
    4) Use top_drops snippet for old→new price
    5) Try product page to upgrade name/price (best-effort)
    """
    deals = []
    unique_asins = OrderedDict()

    # Primary: old pattern
    asin_patterns = list(re.finditer(r'/product/([A-Z0-9]{10})', html))
    # Fallback: direct Amazon links if above returns nothing
    if not asin_patterns:
        asin_patterns = list(re.finditer(r'amazon\.com/dp/([A-Z0-9]{10})', html))

    pcts = re.findall(r'([1-9]\d*(?:\.\d+)?)%', html)

    for idx, match in enumerate(asin_patterns):
        asin = match.group(1)
        if not is_valid_asin(asin) or asin in unique_asins:
            continue
        unique_asins[asin] = True

        # Percent change from the top_drops page (old logic)
        pct = pcts[len(deals)] if len(deals) < len(pcts) else '?'

        # Fallback price parsing from around the match (old behavior-like)
        start = max(0, match.start() - 200)
        end = min(len(html), match.end() + 200)
        snippet = html[start:end]

        snippet_prices = re.findall(r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)', snippet)
        if len(snippet_prices) >= 2:
            old_price = snippet_prices[0]
            new_price = snippet_prices[-1]
            price_change = f"{old_price} → {new_price}"
        elif len(snippet_prices) == 1:
            price_change = f"? → {snippet_prices[0]}"
        else:
            price_change = "? → ?"

        # Basic fallback name like before
        name = f"Deal-{asin[:6]}"

        # Try to get a better name & prices from product page (best effort)
        try:
            prod_url = f"https://camelcamelcamel.com/product/{asin}"
            r = requests.get(prod_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")

            title = soup.find("h1") or soup.find("title")
            if title:
                name = title.get_text().strip().split("|")[0][:60]

            page_text = soup.get_text()
            page_prices = re.findall(r'\$(\d+(?:,\d{3})*\.\d{2})', page_text)
            if len(page_prices) >= 2:
                price_change = f"{page_prices[0]} → {page_prices[-1]}"
            elif page_prices:
                price_change = f"? → {page_prices[-1]}"
        except Exception:
            # Keep fallback name and price_change
            pass

        amazon_url = f"https://www.amazon.com/dp/{asin}"

        deals.append({
            'asin': asin,
            'name': name,
            'pct': pct,
            'price_change': price_change,
            'amazon_url': amazon_url
        })

        if len(deals) == 5:
            break

    print(f"Parsed {len(deals)} deals")
    return deals


def load_seen_urls():
    seen = set()
    if os.path.exists(const.SEEN_FILE):
        with open(const.SEEN_FILE) as f:
            lines = f.read().splitlines()
            for i in range(0, len(lines), 3):  # URL, details, ---
                if i < len(lines):
                    url = lines[i].strip()
                    # keep same pattern as before
                    if '/dp/B' in url:
                        seen.add(url)
    return seen


def append_new_records(new_deals):
    """Append 3-line records: URL + details + separator"""
    if not new_deals:
        return

    with open(const.SEEN_FILE, 'a') as f:
        for deal in new_deals:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            details = f"{deal['name']} | {deal['price_change']} (-{deal['pct']}%) | {timestamp}"
            f.write(f"{deal['amazon_url']}\n")
            f.write(f"{details}\n")
            f.write("---\n")

    print(f"📝 Appended {len(new_deals)} 3-line records w/ separators")


def save_top5(deals):
    with open(const.TOP_FILE, 'w') as f:
        for d in deals:
            f.write(
                f"{d['amazon_url']}\n"
                f"{d['name']} | {d['price_change']} (-{d['pct']}%)\n"
            )


def new_deals(seen, deals):
    return [d for d in deals if d['amazon_url'] not in seen]


def print_deals(deals, new_deals_list):
    print("\n🛒 TOP 5:")
    new_urls = {nd['amazon_url'] for nd in new_deals_list}
    for i, d in enumerate(deals, 1):
        marker = " 🆕" if d['amazon_url'] in new_urls else ""
        print(f"{i}. {d['name']:<40} {d['price_change']} (-{d['pct']}%) {marker}")
        print(f"   {d['amazon_url']}")
    if new_deals_list:
        print(f"\n🎉 {len(new_deals_list)} NEW!")


# Notifications on CMD (old version)
# def notify_new(new_deals):
#     # Keep simple on-terminal notification; swap this for Telegram on Pi
#     for deal in new_deals[:5]:
#         print(f"NEW: {deal['name']} {deal['price_change']} (-{deal['pct']}%) {deal['amazon_url']}")
#         time.sleep(1)

# Notifications on Telegram (new version)
def notify_new(new_deals):
    api_url = f"https://api.telegram.org/bot{const.CC_BOT_TOKEN}/sendMessage"
    for deal in new_deals[:5]:
        text = (f"🛒 *{deal['name']}*\n"
                f"💰 ${deal['price_change']} (-{deal['pct']}%) \n"
                f"🔗 {deal['amazon_url']}")
        try:
            requests.post(api_url, data={
                "chat_id": const.CC_CHAT_ID, 
                "text": text, 
                "parse_mode": "Markdown"
            }, timeout=10)
            time.sleep(1)
        except Exception as e:
            print(f"Telegram fail: {e}")


def main():
    print("📄 3-LINE SEPARATED TRACKER (names + prices)\n")
    seen = load_seen_urls()
    print(f"History: {len(seen)} URLs | {const.SEEN_FILE}")

    while True:
        html = get_html()
        if len(html) < 5000:
            time.sleep(const.POLL_INTERVAL)
            continue

        deals = parse_deals(html)
        new_deals_list = new_deals(seen, deals)

        print_deals(deals, new_deals_list)

        if new_deals_list:
            print("🚨 NEW DEALS!")
            notify_new(new_deals_list)
            append_new_records(new_deals_list)
            for deal in new_deals_list:
                seen.add(deal['amazon_url'])
            save_top5(deals)
            print(f"✅ Added {len(new_deals_list)} records")
        else:
            print("✅ No new")

        print(f"⏳ {const.POLL_INTERVAL}s | {datetime.now().strftime('%H:%M:%S')}\n")
        time.sleep(const.POLL_INTERVAL)


if __name__ == '__main__':
    main()
