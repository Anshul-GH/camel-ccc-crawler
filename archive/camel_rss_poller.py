#!/usr/bin/env python3

import requests
import hashlib
import time
import os
import subprocess

# RSS feed from top_drops page - reliable and bot-friendly
URL = 'https://camelcamelcamel.com/rss/top_drops.rss'  # Adjust if needed; use browser RSS link
HASH_FILE = 'camel_rss_hash.txt'
POLL_INTERVAL = 300  # 5 minutes

def get_page_content(url):
    """Fetch with full browser headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
        'Accept': 'application/rss+xml,application/xml,text/xml;q=0.9,text/html;q=0.8,*/*;q=0.1',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"Fetched successfully: {len(response.text)} chars ({response.headers.get('content-type', 'unknown')})")
        return response.text.encode('utf-8')
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None

def compute_hash(content):
    return hashlib.sha256(content).hexdigest()

def load_hash():
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, 'r') as f:
            return f.read().strip()
    return None

def save_hash(h):
    with open(HASH_FILE, 'w') as f:
        f.write(h)

def send_notification(title, message):
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    subprocess.run(['osascript', '-e', script], check=False)

def main():
    print("CamelCamelCamel Top Drops RSS Monitor...")
    print(f"Polling {URL} every {POLL_INTERVAL // 60} min. Ctrl+C to stop.\n")

    prev_hash = load_hash()
    consecutive_errors = 0

    while True:
        content = get_page_content(URL)
        if content is None:
            consecutive_errors += 1
            print(f"Retry in {POLL_INTERVAL}s...")
            if consecutive_errors >= 3:
                send_notification("Monitor Failed", "RSS fetch errors. Check URL.")
                break
            time.sleep(POLL_INTERVAL)
            continue

        current_hash = compute_hash(content)
        consecutive_errors = 0

        if prev_hash is None:
            print("Baseline RSS hash set.")
            save_hash(current_hash)
            prev_hash = current_hash
        elif current_hash != prev_hash:
            print("TOP DROPS UPDATED!")
            send_notification("Camel Top Drops", "New price drops in RSS feed!")
            save_hash(current_hash)
            prev_hash = current_hash
        else:
            print("No update.")

        print(f"Next poll in {POLL_INTERVAL}s...")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
