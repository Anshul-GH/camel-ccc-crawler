#!/usr/bin/env python3

import re
import time
import os
import subprocess
from datetime import datetime
from collections import OrderedDict

URL = 'https://camelcamelcamel.com/top_drops'
SEEN_FILE = 'seen_urls.txt'
TOP_FILE = 'top5.txt'
POLL_INTERVAL = 60

def is_valid_asin(asin):
    return bool(re.match(r'^B[A-Z0-9]{9}$', asin))

def get_html():
    cmd = ['curl', '-s', '-L', '-A', 'Mozilla/5.0 Mac Safari/605.1.15', '--compressed', URL]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.stdout.decode(errors='ignore')
    except:
        return ''

def parse_deals(html):
    asin_patterns = list(re.finditer(r'/product/([A-Z0-9]{10})', html))
    pcts = re.findall(r'([1-9]\d*(?:\.\d+)?)%', html)
    
    deals = []
    unique_asins = OrderedDict()
    
    for match in asin_patterns[:15]:
        asin = match.group(1)
        if not is_valid_asin(asin) or asin in unique_asins:
            continue
        unique_asins[asin] = True
        
        start = max(0, match.start() - 150)
        end = min(len(html), match.end() + 150)
        snippet = html[start:end].lower()
        name_match = re.search(r'(?:product|item|title)\s*:?\s*([a-z]{3,}[\s\w]{4,40})', snippet)
        name = name_match.group(1).title().strip()[:45] if name_match else f'Deal-{asin[:6]}'
        
        pct = pcts[len(deals)] if len(deals) < len(pcts) else '?'
        amazon_url = f"https://www.amazon.com/dp/{asin}"
        
        deals.append({
            'asin': asin,
            'name': name,
            'pct': pct,
            'amazon_url': amazon_url
        })
        if len(deals) == 5:
            break
    
    print(f"Parsed {len(deals)} deals")
    return deals

def load_seen_urls():
    seen = set()
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            lines = f.read().splitlines()
            for i in range(0, len(lines), 3):  # Every 3rd line pattern (URL, details, ---)
                if i < len(lines):
                    url = lines[i].strip()
                    if '/dp/B[A-Z0-9]{9}' in url:
                        seen.add(url)
    return seen

def append_new_records(new_deals):
    """Append 3-line records: URL + details + separator"""
    if not new_deals:
        return
    
    with open(SEEN_FILE, 'a') as f:
        for deal in new_deals:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            details = f"{deal['name']} | {deal['pct']} | {timestamp}"
            f.write(f"{deal['amazon_url']}\n")
            f.write(f"{details}\n")
            f.write("---\n")
    
    print(f"📝 Appended {len(new_deals)} 3-line records w/ separators")

def save_top5(deals):
    with open(TOP_FILE, 'w') as f:
        for d in deals:
            f.write(f"{d['amazon_url']}\n{d['name']} | {d['pct']}%\n")

def new_deals(seen, deals):
    return [d for d in deals if d['amazon_url'] not in seen]

def print_deals(deals, new_deals):
    print("\n🛒 TOP 5:")
    for i, d in enumerate(deals, 1):
        marker = " 🆕" if d['amazon_url'] in [nd['amazon_url'] for nd in new_deals] else ""
        print(f"{i}. {d['name']:<38} (-{d['pct']}%) {marker}")
        print(f"   {d['amazon_url']}")
    if new_deals:
        print(f"\n🎉 {len(new_deals)} NEW!")

def notify_new(new_deals):
    for deal in new_deals[:2]:
        subprocess.run([
            'osascript', '-e', 
            f'display notification "{deal["name"]} -{deal["pct"]}%" with title "🆕 Deal" subtitle "{deal["amazon_url"]}" sound name "Glass"'
        ], check=False)
        time.sleep(1)

def main():
    print("📄 3-LINE SEPARATED TRACKER\n")
    seen = load_seen_urls()
    print(f"History: {len(seen)} URLs | {SEEN_FILE}")
    
    while True:
        html = get_html()
        if len(html) < 5000:
            time.sleep(POLL_INTERVAL)
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
        
        print(f"⏳ {POLL_INTERVAL}s | {datetime.now().strftime('%H:%M:%S')}\n")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
