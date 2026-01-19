#!/usr/bin/env python3

import requests
import hashlib
import time
import os
import subprocess

URL = 'https://camelcamelcamel.com/top_drops'
HASH_FILE = 'camel_hash.txt'
POLL_INTERVAL = 300  # 5 minutes in seconds

def get_page_content(url):
    """Fetch page content with full browser headers to bypass 403."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"Fetched successfully: {len(response.text)} chars")
        return response.text.encode('utf-8')
    except requests.RequestException as e:
        print(f"Error fetching URL: {e}")
        return None

def compute_hash(content):
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content).hexdigest()

def load_hash():
    """Load previous hash from file."""
    if os.path.exists(HASH_FILE):
        with open(HASH_FILE, 'r') as f:
            return f.read().strip()
    return None

def save_hash(h):
    """Save hash to file."""
    with open(HASH_FILE, 'w') as f:
        f.write(h)

def send_notification(title, message):
    """Send macOS desktop notification with sound."""
    script = f'''
    display notification "{message}" with title "{title}" sound name "Glass"
    '''
    subprocess.run(['osascript', '-e', script], check=False)

def main():
    print("Starting CamelCamelCamel top drops monitor...")
    print(f"Polling {URL} every {POLL_INTERVAL // 60} minutes.")
    print("Press Ctrl+C to stop.\n")

    prev_hash = load_hash()
    consecutive_errors = 0

    while True:
        content = get_page_content(URL)
        if content is None:
            consecutive_errors += 1
            print(f"Next check in {POLL_INTERVAL} seconds...")
            if consecutive_errors >= 3:
                send_notification("Monitor Error", "Too many fetch errors. Check connection.")
                break
            time.sleep(POLL_INTERVAL)
            continue

        current_hash = compute_hash(content)
        consecutive_errors = 0  # Reset on success

        if prev_hash is None:
            print("Initial baseline set.")
            save_hash(current_hash)
            prev_hash = current_hash
        elif current_hash != prev_hash:
            print("CHANGE DETECTED!")
            send_notification("CamelCamelCamel Updated", "Top drops page has new content!")
            save_hash(current_hash)
            prev_hash = current_hash
        else:
            print("No change.")

        print(f"Next check in {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()
