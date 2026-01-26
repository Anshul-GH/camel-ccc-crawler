#!/usr/bin/env python3
import re
import time
import os
import subprocess
import json
from datetime import datetime, timedelta
from collections import OrderedDict

import constants as const
import requests
from bs4 import BeautifulSoup

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def is_valid_asin(asin: str) -> bool:
    return bool(re.fullmatch(r'[A-Z][A-Z0-9]{9}', asin))


def get_html() -> str:
    cmd = [
        "curl",
        "-s",
        "-L",
        "-A",
        "Mozilla/5.0 (Mac) Safari/605.1.15",
        "--compressed",
        const.URL,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.stdout.decode(errors="ignore")
    except Exception:
        return ""


def parse_deals(html: str):
    """Parse ALL deals from the top_drops page, with improved name/price parsing."""
    deals = []
    unique_asins = OrderedDict()

    # Primary: /product/ASIN; fallback: amazon.com/dp/ASIN
    asin_patterns = list(re.finditer(r"/product/([A-Z][A-Z0-9]{9})", html))
    if not asin_patterns:
        asin_patterns = list(re.finditer(r"amazon\.com/dp/([A-Z][A-Z0-9]{9})", html))


    # Rough percent list; later we pick idx-based or fallback to '?'
    pcts = re.findall(r"[-+]?\d+\.?\d*%?", html)

    for idx, match in enumerate(asin_patterns):
        asin = match.group(1)
        if not is_valid_asin(asin) or asin in unique_asins:
            continue
        unique_asins[asin] = True

        # Name: search nearby h3/a text
        name_start = max(0, match.start() - 500)
        name_end = min(len(html), match.start() + 200)
        name_snippet = html[name_start:name_end]

        name_match = re.search(
            r"(?i)(?:<h3[^>]*>|<a[^>]*product[^>]*>)\s*([^<>\n]{10,120}?)(?=\s*(?:<|€|$))",
            name_snippet,
        )
        name = name_match.group(1).strip() if name_match else f"Deal-{asin[:6]}"

        # Prices: search nearby snippet for "old/prev/was" and "now/current/lowest"
        snippet_start = max(0, match.start() - 400)
        snippet_end = min(len(html), match.end() + 400)
        snippet = html[snippet_start:snippet_end].lower()

        old_match = re.search(
            r"(?:old|prev|was)[:\s]*\$?([0-9,]+\.\d{2})", snippet
        )
        new_match = re.search(
            r"(?:now|current|lowest)[:\s]*\$?([0-9,]+\.\d{2})", snippet
        )
        old_price = old_match.group(1) if old_match else "?"
        new_price = new_match.group(1) if new_match else "?"

        pct = pcts[idx] if idx < len(pcts) and pcts[idx] else "?"
        price_change = f"{old_price} → {new_price} ({pct})"

        # Best-effort enhancement from camelcamelcamel product page
        try:
            prod_url = f"https://camelcamelcamel.com/product/{asin}"
            r = requests.get(
                prod_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10
            )
            soup = BeautifulSoup(r.text, "html.parser")

            title_tag = soup.find("h1") or soup.find("title")
            if title_tag:
                cleaned = title_tag.get_text().strip()
                # Often titles are "Name – CamelCamelCamel" etc.
                name = cleaned.split(" - ")[0].split(" – ")[0][:120]

            page_text = soup.get_text()
            page_prices = re.findall(r"[0-9,]+\.\d{2}", page_text)[:2]
            if len(page_prices) == 2:
                price_change = f"{page_prices[0]} → {page_prices[1]} ({pct})"
        except Exception:
            pass

        amazon_url = f"https://www.amazon.com/dp/{asin}"
        deals.append(
            {
                "asin": asin,
                "name": name,
                "pct": pct,
                "pricechange": price_change,
                "amazon_url": amazon_url,
            }
        )

    print(f"Parsed {len(deals)} deals")
    return deals

def is_critical(deal):
    pct_str = deal['pct']
    # pct_match = re.search(r'(\d+)', pct_str)
    # pct = float(pct_match.group(1)) if pct_match else 0
    pct_match = re.search(r'(\d+(?:\.\d+)?)', pct_str.replace('%', ''))
    pct = float(pct_match.group(1)) if pct_match else 0
    name_lower = deal['name'].lower()
    # return pct >= const.MIN_DROP_PCT and any(kw.lower() in name_lower for kw in const.KEYWORDS)
    has_drop = pct >= const.MIN_DROP_PCT
    has_keyword = any(kw.lower() in name_lower for kw in const.KEYWORDS)
    return has_drop or has_keyword


def load_seen_urls(max_age_hours: int = 24):
    """
    Load seen URLs from SEEN_FILE, auto-purging records older than max_age_hours.

    File format (3 lines per record):
      1: URL
      2: name | pricechange | pct | YYYY-MM-DD HH:MM:SS
      3: ---
    """
    seen = set()
    fresh_lines = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    if not os.path.exists(const.SEEN_FILE):
        return seen

    with open(const.SEEN_FILE) as f:
        lines = f.read().splitlines()

    for i in range(0, len(lines), 3):
        if i + 1 >= len(lines):
            continue

        url = lines[i].strip()
        details = lines[i + 1].strip()

        parts = [p.strip() for p in details.split("|")]
        ts_str = parts[-1] if parts else ""

        try:
            ts = datetime.strptime(ts_str, TIME_FORMAT)
        except Exception:
            # If parsing fails, keep record but don't add to seen
            fresh_lines.extend(lines[i : i + 3])
            continue

        if ts >= cutoff:
            # Fresh: keep record and mark URL as seen
            fresh_lines.extend(lines[i : i + 3])
            if "amazon.com/dp/" in url:
                seen.add(url)
        else:
            # Old: drop, effectively purging old seen entries
            pass

    # Rewrite file with only fresh records
    with open(const.SEEN_FILE, "w") as f:
        for line in fresh_lines:
            f.write(line + "\n")

    print(
        f"Loaded {len(seen)} seen URLs after purge; "
        f"kept {len(fresh_lines)//3} records in {const.SEEN_FILE}"
    )
    return seen


def append_new_records(newdeals):
    """Append 3-line records: URL / details / --- with timestamp for purge."""
    if not newdeals:
        return

    with open(const.SEEN_FILE, "a") as f:
        for deal in newdeals:
            timestamp = datetime.now().strftime(TIME_FORMAT)
            details = (
                f"{deal['name']} | {deal['pricechange']} | {deal['pct']} | {timestamp}"
            )
            f.write(f"{deal['amazon_url']}\n")
            f.write(details + "\n")
            f.write("---\n")

    print(f"Appended {len(newdeals)} records to {const.SEEN_FILE}")


def save_all_deals(deals):
    """Save all parsed deals into TOP_FILE (replaces old top5 behavior)."""
    with open(const.TOP_FILE, "w") as f:
        for d in deals:
            f.write(
                f"{d['amazon_url']} | {d['name']} | {d['pricechange']} | {d['pct']}\n"
            )
    print(f"Saved {len(deals)} deals to {const.TOP_FILE}")


def load_price_state():
    if os.path.exists(const.STATE_FILE):
        try:
            with open(const.STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_price_state(state: dict):
    with open(const.STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def new_deals(seen, deals):
    """Return only deals whose URL is not in the seen set."""
    return [d for d in deals if d["amazon_url"] not in seen]


def print_deals(deals, newdeals_list):
    new_urls = {nd["amazon_url"] for nd in newdeals_list}
    print("=== TOP DROPS ===")
    for i, d in enumerate(deals, 1):
        marker = "🔥 CRITICAL!" if is_critical(d) else ("NEW!" if d['amazon_url'] in new_urls else " ")
        print(f"{i:2d}. {d['name'][:60]:<60} {d['pricechange']:>25} {marker}")
        print(f"     🔗 {d['amazon_url']}")
    if newdeals_list:
        print(f"\n🚨 {len(newdeals_list)} NEW DEALS!")

def notify_new(newdeals):
    api_url = f"https://api.telegram.org/bot{const.CC_BOT_TOKEN}/sendMessage"
    critical = [d for d in newdeals if is_critical(d)]
    regular = [d for d in newdeals if not is_critical(d)]
    
    if critical:
        drop_pct = const.MIN_DROP_PCT
        text = "*🔥 CRITICAL DEALS (>{drop_pct} percent drop OR keywords):*\n\n"
        for d in critical:
            text += f"*{d['name']}*\n{d['pricechange']} ({d['pct']})\n{d['amazon_url']}\n\n"
            # text += f"*{d['name']}*\n{d['pricechange']} ({d['pct']})\n{d['amazon_url']}\n\n"
            # Add: text = text.replace('\\', '\\\\').replace('_', '\\_') before requests.post

        try:
            text = text.replace('_', '\\_').replace('[', '\\[')[:4000]
            requests.post(api_url, data={
                'chat_id': const.CC_CHAT_ID, 
                'text': text, 
                'parse_mode': 'Markdown', 
                'disable_web_page_preview': True
            }, timeout=10)
            print(f"Sent {len(critical)} CRITICAL alerts")
        except Exception as e:
            print(f"Telegram CRITICAL fail: {e}")
    
    if regular:
        for deal in regular:
            text = f"{deal['name']}\n{deal['pricechange']} ({deal['pct']})\n{deal['amazon_url']}"
            try:
                text = text.replace('_', '\\_').replace('[', '\\[')[:4000]
                requests.post(api_url, data={
                    'chat_id': const.CC_CHAT_ID, 
                    'text': text, 
                    'parse_mode': 'Markdown', 
                    'disable_web_page_preview': True
                }, timeout=10)
                time.sleep(0.5)
            except Exception as e:
                print(f"Telegram regular fail: {e}")



def main():
    print("=== CamelCamelCamel Top Drops Tracker (ALL deals + daily purge) ===")

    # Load & purge seen URLs older than 24h
    seen = load_seen_urls(max_age_hours=24)

    while True:
        html = get_html()
        if len(html) < 5000:
            print("Short HTML, retrying...")
            time.sleep(const.POLL_INTERVAL)
            continue

        deals = parse_deals(html)
        newdeals_list = new_deals(seen, deals)
        print_deals(deals, newdeals_list)

        # Update price state for all parsed deals
        state = load_price_state()
        for d in deals:
            asin = d["asin"]
            new_p_match = re.search(
                r"→\s*\$?([0-9,]+\.\d{2})", d["pricechange"]
            )
            if new_p_match:
                new_p = float(new_p_match.group(1).replace(",", ""))
                state[asin] = {
                    "name": d["name"],
                    "last_price": new_p,
                    "last_seen": datetime.now().isoformat(),
                }
        save_price_state(state)

        if newdeals_list:
            print("🚨 SENDING ALERTS!")
            notify_new(newdeals_list)
            append_new_records(newdeals_list)
            for deal in newdeals_list:
                seen.add(deal["amazon_url"])
        else:
            print("No new deals.")

        save_all_deals(deals)
        print(
            f"Next poll in {const.POLL_INTERVAL}s... "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )
        time.sleep(const.POLL_INTERVAL)


if __name__ == "__main__":
    main()
