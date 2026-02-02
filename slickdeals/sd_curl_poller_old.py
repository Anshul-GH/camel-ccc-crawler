#!/usr/bin/env python3
import re
import time
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import constants as const  # import SD_* constants

TIMEFORMAT = "%Y-%m-%d %H:%M:%S"

def referral_link(original_link: str, user_id: str) -> str:
    """Convert https://slickdeals.net/f/1234567-xyz to /sh/thread-1234567/e/29/c/deal-details/u/{user_id}/"""
    match = re.search(r'/f/(\d+)', original_link)
    if match:
        thread_id = match.group(1)
        return f"https://slickdeals.net/sh/thread-{thread_id}/e/29/c/deal-details/u/{user_id}/"
    return original_link  # fallback if not /f/

def load_sd_seen(max_age_hours: int = 24):
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
        meta = lines[i+1].strip()
        parts = [p.strip() for p in meta.split(" || ")]
        ts_str = parts[-1] if len(parts) > 1 and "likes=" in parts[-1] else ""
        try:
            ts = datetime.strptime(ts_str, TIMEFORMAT)
        except Exception:
            fresh_lines.extend(lines[i:i+3])
            continue
        if ts < cutoff:
            continue  # purge old
        fresh_lines.extend(lines[i:i+3])
        seen.add(url)
    with open(const.SD_SEENFILE, "w") as f:
        for line in fresh_lines:
            f.write(line + "\n")
    print(f"Loaded {len(seen)} seen Slickdeals URLs ({len(fresh_lines)//3} records kept)")
    return seen

def append_sd_seen(new_items):
    if not new_items:
        return
    with open(const.SD_SEENFILE, "a") as f:
        for it in new_items:
            ts = datetime.now().strftime(TIMEFORMAT)
            meta = f"{it['title']} || likes={it['likes']} || {ts}"
            f.write(it["link"] + "\n")  # original link for seen check
            f.write(meta + "\n")
            f.write("---\n")
    print(f"Appended {len(new_items)} new records to {const.SD_SEENFILE}")

def fetch_rss():
    resp = requests.get(const.SD_RSS_URL, timeout=20, headers={
        "User-Agent": "Mozilla/5.0 (Mac; Safari/605.1.15)"
    })
    resp.raise_for_status()
    return resp.text

def parse_items(xml_text):
    ns = {"slash": "http://purl.org/rss/1.0/modules/slash/"}
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        likes_text = item.findtext("slash:comments", namespaces=ns) or "0"
        try:
            likes = int(likes_text)
        except ValueError:
            likes = 0
        if likes >= const.MIN_LIKES:
            items.append({
                "title": title,
                "link": link,
                "ref_link": referral_link(link, const.SD_USERID),
                "likes": likes,
            })
    return items

def filter_new(items, seen):
    return [it for it in items if it["link"] not in seen]

def send_sd_alerts(items):
    if not items:
        return
    api_url = f"https://api.telegram.org/bot{const.SD_BOTTOKEN}/sendMessage"
    text_lines = [f"🔥 Slickdeals Hot Deals (≥ {const.MIN_LIKES} likes):"]
    for it in items:
        text_lines.append(f"**{it['title']}** ({it['likes']} 👍)")
        text_lines.append(it['ref_link'])
        text_lines.append("")  # spacer
    text = "\n".join(text_lines)[:4000]
    try:
        requests.post(
            api_url,
            data={
                "chat_id": const.SD_CHATID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,  # enable preview on ref link
            },
            timeout=10,
        )
        print(f"Sent {len(items)} Slickdeals alerts via new bot")
    except Exception as e:
        print("Telegram send failed:", e)

def main():
    print("Slickdeals RSS Poller: ≥ 4 likes → Referral alerts via dedicated bot")
    seen = load_sd_seen()
    while True:
        try:
            xml = fetch_rss()
            items = parse_items(xml)
            new_hot = filter_new(items, seen)
            if new_hot:
                print(f"Found {len(new_hot)} new hot deals")
                send_sd_alerts(new_hot)
                append_sd_seen(new_hot)
                for it in new_hot:
                    seen.add(it["link"])
            else:
                print("No new hot deals")
        except Exception as e:
            print("Poll error:", e)
        print(f"Next poll in {const.POLLINTERVAL}s... ({datetime.now().strftime('%H:%M:%S')})")
        time.sleep(const.POLLINTERVAL)

if __name__ == "__main__":
    main()
