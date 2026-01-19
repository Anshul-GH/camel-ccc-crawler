#!/usr/bin/env python3

import os
import hashlib
import re
import time
import subprocess
from datetime import datetime

URL = 'https://camelcamelcamel.com/top_drops'
HASH_FILE = 'page_hash.txt'
POLL_INTERVAL = 30

def get_page():
    cmd = ['curl', '-s', '-L', '-A', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15', '--compressed', URL]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        content = result.stdout.decode(errors='ignore')
        print(f"📥 {len(content)} chars | Hash preview: {hashlib.md5(content.encode()).hexdigest()[:8]}")
        return content
    except:
        print("❌ Fetch failed")
        return ''

def parse_drops(html):
    print("\n🔍 DEBUG EXTRACTION:")
    
    # ALL product links on page
    all_asins = re.findall(r'/product/([A-Z0-9]{10})', html)
    all_names = re.findall(r'href="/product/[A-Z0-9]{10}"[^>]*>([^<]{3,60}?)<\/a>', html)
    all_pcts = re.findall(r'([1-9]\d*(?:\.\d+)?)%', html)  # Non-zero %
    
    print(f"  ASINs found: {len(all_asins)} | Sample: {all_asins[:4]}")
    print(f"  Names found: {len(all_names)} | Sample: {all_names[:3]}")
    print(f"  % drops: {len(all_pcts)} | Sample: {all_pcts[:4]}")
    
    # Top drops = first 5 ASINs (table order)
    drops = []
    for i in range(min(5, len(all_asins))):
        drops.append({
            'asin': all_asins[i],
            'name': all_names[i] if i < len(all_names) else 'Hot Item',
            'pct': all_pcts[i] if i < len(all_pcts) else '?'
        })
    
    print(f"  → Parsed top 5: {len(drops)} items")
    return drops

def print_drops(drops):
    print("\n🏆 TOP 5:")
    for i, d in enumerate(drops, 1):
        print(f"  {i}. {d['name']:<35} [{d['asin']}]  {d['pct']}% off")

def get_hash(content):
    return hashlib.md5(content.encode()).hexdigest()

def load_hash():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE) as f:
            return f.read().strip()
    return None

def save_hash(h):
    with open(HASH_FILE, 'w') as f:
        f.write(h)

def notify(title, msg):
    subprocess.run(['osascript', '-e', f'display notification "{msg}" with title "{title}" sound name "Glass"'], check=False)

def main():
    print("🐛 FULL DEBUG Monitor\n")
    prev_hash = load_hash()
    
    while True:
        html = get_page()
        if not html:
            time.sleep(POLL_INTERVAL)
            continue
        
        current_hash = get_hash(html)
        drops = parse_drops(html)
        print_drops(drops)
        
        changed = current_hash != prev_hash
        print(f"\n{'🚨 PAGE CHANGED!' if changed else '✅ Stable'} (size shift detected)")
        
        if changed:
            if drops:
                top = f"{drops[0]['name'][:30]} [{drops[0]['asin']}]"
            else:
                top = "Top drops list updated"
            print("🔔 ALERTING...")
            notify("CamelCamelCamel", top)
            save_hash(current_hash)
            prev_hash = current_hash
        
        print(f"⏳ {POLL_INTERVAL}s | {datetime.now().strftime('%H:%M:%S')}\n")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
