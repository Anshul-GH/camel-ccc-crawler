#!/usr/bin/env python3

import re
import time
import os
import subprocess
from datetime import datetime

URL = 'https://camelcamelcamel.com/top_drops'
ASIN_FILE = 'top5_asins.txt'
POLL_INTERVAL = 60

def get_html():
    cmd = ['curl', '-s', '-L', '-A', 'Mozilla/5.0 Mac Safari/605.1.15', '--compressed', URL]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.stdout.decode(errors='ignore')
    except:
        return ''

def parse_deals(html):
    """Extract top 5 from PROVEN patterns"""
    asins = re.findall(r'/product/([A-Z0-9]{10})', html)[:10]
    pcts = re.findall(r'([1-9]\d*(?:\.\d*)?)%', html)[:10]
    
    # Name fallback: text between ASIN links or default
    names = ['Top Deal #' + str(i+1) for i in range(5)]
    
    deals = []
    for i in range(min(5, len(asins))):
        asin = asins[i]
        pct = pcts[i] if i < len(pcts) else '?'
        amazon_url = f"https://amazon.com/dp/{asin}"
        deals.append({
            'asin': asin,
            'name': names[i],
            'pct': pct,
            'amazon_url': amazon_url
        })
    
    print(f"✅ Parsed {len(deals)} deals (ASINs: {len(asins)}, %: {len(pcts)})")
    return deals

def print_deals(deals):
    print("\n🛒 TOP AMAZON DEALS:")
    for i, d in enumerate(deals, 1):
        print(f"{i}. {d['name']:<35} (-{d['pct']}%)")
        print(f"   🔗 {d['amazon_url']}")
    print()

def load_asins():
    if os.path.exists(ASIN_FILE):
        with open(ASIN_FILE) as f:
            return [line.strip() for line in f]
    return []

def save_asins(deals):
    asins = [d['asin'] for d in deals]
    with open(ASIN_FILE, 'w') as f:
        f.write('\n'.join(asins))

def changed(prev, deals):
    prev_top = set(prev[:5])
    curr_top = set(d['asin'] for d in deals)
    return prev_top != curr_top

def alert(deals):
    if deals:
        top = f"{deals[0]['name']} {deals[0]['pct']}% off"
        subprocess.run([
            'osascript', '-e', 
            f'display notification "{top}" with title "🛒 Amazon Deal" subtitle "{deals[0]["amazon_url"]}" sound name "Glass"'
        ], check=False)

def main():
    print("🔥 Reliable Amazon Deals Monitor\n")
    prev_asins = load_asins()
    
    while True:
        html = get_html()
        if len(html) < 5000:  # Sanity
            print("⚠️  Short page")
            time.sleep(POLL_INTERVAL)
            continue
        
        deals = parse_deals(html)
        print_deals(deals)
        
        if changed(prev_asins, deals):
            print("🎉 NEW TOP DEALS!")
            alert(deals)
            save_asins(deals)
            prev_asins = [d['asin'] for d in deals]
        else:
            print("✅ Stable")
        
        print(f"⏳ {POLL_INTERVAL}s | {datetime.now().strftime('%H:%M:%S')}\n")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
