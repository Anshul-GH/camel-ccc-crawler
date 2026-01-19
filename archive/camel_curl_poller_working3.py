#!/usr/bin/env python3

import re
import time
import os
import subprocess
from datetime import datetime
from collections import OrderedDict

URL = 'https://camelcamelcamel.com/top_drops'
ASIN_FILE = 'unique_asins.txt'
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

def parse_unique_deals(html):
    """Unique VALID ASINs only"""
    candidates = re.findall(r'/product/([A-Z0-9]{10})', html)
    pcts = re.findall(r'([1-9]\d*(?:\.\d+)?)%', html)
    
    # Filter VALID + UNIQUE ASINs (preserve order)
    unique_valid = OrderedDict()
    for asin in candidates:
        if is_valid_asin(asin) and asin not in unique_valid:
            unique_valid[asin] = True
    
    valid_asins = list(unique_valid.keys())
    print(f"Found {len(candidates)} → {len(valid_asins)} UNIQUE VALID ASINs")
    print(f"Top unique: {valid_asins[:4]}")
    
    deals = []
    for i, asin in enumerate(valid_asins[:10]):
        pct = pcts[i] if i < len(pcts) else '?'
        amazon_url = f"https://www.amazon.com/dp/{asin}"
        deals.append({
            'asin': asin,
            'name': f"Deal #{i+1}",
            'pct': pct,
            'amazon_url': amazon_url
        })
    
    return deals[:5]

def print_deals(deals):
    print("\n🛒 TOP 5 UNIQUE DEALS:")
    for i, d in enumerate(deals, 1):
        print(f"{i}. Deal #{i} [{d['asin']}]  (-{d['pct']}%)")
        print(f"   🛒 {d['amazon_url']}")
    print()

def load_asins():
    if os.path.exists(ASIN_FILE):
        with open(ASIN_FILE) as f:
            return [line.strip() for line in f if is_valid_asin(line.strip())]
    return []

def save_asins(deals):
    with open(ASIN_FILE, 'w') as f:
        f.write('\n'.join(d['asin'] for d in deals))

def top_changed(prev, deals):
    return set(prev[:5]) != set(d['asin'] for d in deals)

def notify(deals):
    top_asin = deals[0]['asin']
    top_pct = deals[0]['pct']
    url = deals[0]['amazon_url']
    subprocess.run([
        'osascript', '-e', 
        f'display notification "B{top_asin} -{top_pct}%" with title "🛒 New Deal" subtitle "{url}" sound name "Glass"'
    ], check=False)

def main():
    print("🔥 UNIQUE VALID ASIN Monitor\n")
    prev_asins = load_asins()
    
    while True:
        html = get_html()
        if len(html) < 5000:
            time.sleep(POLL_INTERVAL)
            continue
        
        deals = parse_unique_deals(html)
        print_deals(deals)
        
        if top_changed(prev_asins, deals):
            print("🎉 NEW TOP DEALS!")
            notify(deals)
            save_asins(deals)
            prev_asins = [d['asin'] for d in deals]
        else:
            print("✅ Stable")
        
        print(f"⏳ {POLL_INTERVAL}s | {datetime.now().strftime('%H:%M:%S')}\n")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
