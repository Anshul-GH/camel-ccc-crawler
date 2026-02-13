#!/usr/bin/env python3

import re
import time
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import constants as const


def referral_link(original_link: str, user_id: str) -> str:
    """
    Convert https://slickdeals.net/f/{thread_id}-whatever
    to a short referral form:
    https://slickdeals.net/sh/thread-{thread_id}/e/3/c/deal-details/u/{user_id}/
    """
    match = re.search(r"/f/(\d+)", original_link)
    if match:
        thread_id = match.group(1)
        return f"https://slickdeals.net/sh/thread-{thread_id}/e/3/c/deal-details/u/{user_id}/"
    return original_link

def load_sd_seen(max_age_hours: int = 24):
    """
    Load seen URLs from SD_SEENFILE, auto-purging records older than max_age_hours.
    File format (3 lines per record):
      1: URL
      2: title || likes=N || YYYY-MM-DD HH:MM:SS
      3: ---
    """
    seen = set()
    fresh_lines = []
    cutoff = datetime.now() - timedelta(hours=max_age_hours)

    if not os.path.exists(const.SD_SEENFILE):
        return seen

    with open(const.SD_SEENFILE) as f:
        lines = f.read().splitlines()

    for i in range(0, len(lines), 3):
        if i + 1 >= len(lines):
            continue
        url = lines[i].strip()
        meta = lines[i + 1].strip()
        parts = [p.strip() for p in meta.split("||")]
        ts_str = parts[-1] if parts else ""

        try:
            ts = datetime.strptime(ts_str, const.TIMEFORMAT)
        except Exception:
            # If parsing fails, keep the record but don't add to seen
            fresh_lines.extend(lines[i : i + 3])
            continue

        if ts < cutoff:
            # Too old → drop
            continue

        fresh_lines.extend(lines[i : i + 3])
        seen.add(url)

    with open(const.SD_SEENFILE, "w") as f:
        for line in fresh_lines:
            f.write(line + "\n")

    print(
        f"[seen] Loaded {len(seen)} URLs, kept {len(fresh_lines)//3} records in {const.SD_SEENFILE}"
    )
    return seen


def append_sd_seen(new_items):
    """Append new records to SD_SEENFILE."""
    if not new_items:
        return
    with open(const.SD_SEENFILE, "a") as f:
        for it in new_items:
            ts = datetime.now().strftime(const.TIMEFORMAT)
            meta = f"{it['title']} || likes={it['likes']} || {ts}"
            f.write(it["link"] + "\n")  # store the original SD link as key
            f.write(meta + "\n")
            f.write("---\n")
    print(f"[seen] Appended {len(new_items)} records to {const.SD_SEENFILE}")


def fetch_all_rss():
    """Fetch BOTH Frontpage + Popular RSS feeds."""
    all_items = []
    
    for i, rss_url in enumerate(const.SD_RSS_URLS, 1):
        print(f"[DEBUG] Fetching RSS #{i}: {rss_url.split('?')[0]}...")
        try:
            resp = requests.get(
                rss_url,
                timeout=20,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X)"},
            )
            resp.raise_for_status()
            items = parse_items(resp.text, source=f"RSS#{i}")
            all_items.extend(items)
        except Exception as e:
            print(f"[DEBUG] RSS#{i} failed: {e}")
    
    # FIXED: Efficient set-based deduplication (no dead code)
    seen_links = set()
    unique_items = []
    for item in all_items:
        link = item['link']
        if link not in seen_links:
            seen_links.add(link)
            unique_items.append(item)
    
    print(f"[DEBUG] Combined {len(all_items)} → {len(unique_items)} unique deals")
    return unique_items

def parse_items(xml_text, source):
    """Parse single RSS feed. Returns ALL items (MIN_LIKES=0 strategy)."""
    ns = {'slash': 'http://purl.org/rss/1.0/modules/slash/'}
    root = ET.fromstring(xml_text)
    all_items = root.findall('.//item')
    print(f"[DEBUG] {source}: {len(all_items)} items found")
    
    items = []
    junk_keywords = ['Sample', 'Survey', 'Giveaway', 'Sweepstakes', 'YMMV']
    
    for idx, item in enumerate(all_items[:20]):  # Limit to newest 20
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        
        # Bulletproof likes parsing - defaults to 0
        likestext = "0"
        try:
            comments_elem = (item.find('comments') or 
                           item.find('{http://purl.org/rss/1.0/modules/slash/}comments'))
            if comments_elem is not None and comments_elem.text:
                likestext = comments_elem.text
            likes = int(likestext) if likestext.isdigit() else 0
        except:
            likes = 0
        
        if not link:
            continue
            
        # Quality filters
        if likes < const.MIN_LIKES:
            continue
            
        if any(kw in title.upper() for kw in junk_keywords):
            continue
            
        # Optional: Price filter (uncomment if wanted)
        # if '$' not in title:
        #     continue
            
        items.append({
            'title': title,
            'link': link, 
            'likes': likes,
            'ref_link': referral_link(link, const.SD_USERID),
            'source': source
        })
        
    print(f"[DEBUG] {source}: {len(items)} qualifying {const.MIN_LIKES}+ likes")
    return items


def filter_new(items, seen):
    """Return only items whose original link is not in seen."""
    return [it for it in items if it["link"] not in seen]

def send_sd_alerts(items):
    """Send EACH URL as SEPARATE message to ALL chats WITH LINK PREVIEWS."""
    if not items:
        return
        
    api_url = f"https://api.telegram.org/bot{const.SD_BOTTOKEN}/sendMessage"
    
    for item in items:
        ref_link = item["ref_link"]
        title_short = item["title"][:100]
        
        # Send to EVERY chat ID (group + private)
        for chat_id in const.SD_CHATIDS:
            try:
                text = f"🔥 {title_short}\n{ref_link}"
                
                r = requests.post(api_url, data={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                }, timeout=10)
                print(f"[telegram] → {chat_id}: {title_short[:50]}... (w/ preview)")
                
                time.sleep(0.5)  # Rate limit protection
                
            except Exception as e:
                print(f"[telegram] {chat_id} ERROR: {e}")

def main():
    print(
        f"Slickdeals RSS Poller: likes >= {const.MIN_LIKES} → referral alerts via dedicated bot"
    )

    seen = load_sd_seen(max_age_hours=24)

    while True:
        try:
            items = fetch_all_rss()
            new_hot = filter_new(items, seen)

            if new_hot:
                print(f"[poll] {len(new_hot)} new hot items")
                append_sd_seen(new_hot)  # mark as seen first
                for it in new_hot:
                    print(f"  {it['likes']} 👍  {it['title']}")
                    print(f"    {it['ref_link']}")
                send_sd_alerts(new_hot)
                for it in new_hot:
                    seen.add(it["link"])

            else:
                print("[poll] No new hot items")

        except Exception as e:
            print("[poll] Error:", e)

        now = datetime.now().strftime("%H:%M:%S")
        print(f"[poll] Next poll in {const.POLLINTERVAL}s... ({now})")
        time.sleep(const.POLLINTERVAL)


if __name__ == "__main__":
    main()
