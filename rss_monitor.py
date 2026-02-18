#!/usr/bin/env python3
"""
Avto.net RSS monitor: watch an RSS feed for new car listings and notify (Telegram or console).
Uses feedparser; no HTML scraping. Idempotent and safe for repeated runs (e.g. every 30 min).
"""

import json
import os
from datetime import datetime

import feedparser
import requests

# =============================================================================
# CONFIGURATION
# =============================================================================
#
# RSS feed URL: use the avto.net RSS URL that already includes your filters.
# - Build your search on https://www.avto.net (brand, model, year, price, fuel, etc.).
# - Look for an RSS / "RSS" link on the results page, or try:
#   https://www.avto.net/Ads/results_rss.asp?<same query params as results.asp>
#   Example params: znamka=Hyundai&model=ix35&cenaMin=0&cenaMax=7000&letnikMin=2010&letnikMax=2090
# - To add/remove filters: change the query string in the URL (e.g. &bencin=1 for diesel).
# - Paste the full URL below.
#
RSS_FEED_URL = (
    "https://www.avto.net/Ads/results_rss.asp?"
    "znamka=Hyundai&model=ix35&cenaMin=0&cenaMax=7000&letnikMin=2010&letnikMax=2090"
)

# File to store already-seen listing URLs (persistent across runs).
SEEN_FILE = "seen_rss.json"

# Telegram (from environment). Fallback: print to console.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =============================================================================
# FETCH FEED
# =============================================================================


def fetch_feed(url):
    """
    Fetch and parse the RSS feed. Returns a list of entries, each with:
    - title, link, published (parsed date or None).
    Returns [] on fetch/parse error.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching feed: {e}")
        return []

    try:
        parsed = feedparser.parse(response.content)
    except Exception as e:
        print(f"Error parsing feed: {e}")
        return []

    entries = []
    for e in getattr(parsed, "entries", []):
        link = (e.get("link") or "").strip()
        if not link:
            continue
        entries.append({
            "title": (e.get("title") or "").strip(),
            "link": link,
            "published": e.get("published"),
        })
    return entries


# =============================================================================
# SEEN LIST PERSISTENCE
# =============================================================================


def load_seen():
    """Load set of already-seen listing URLs from SEEN_FILE. Returns set of URLs."""
    if not os.path.exists(SEEN_FILE):
        return set()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict) and "urls" in data:
            return set(data["urls"])
        return set()
    except Exception as e:
        print(f"Error loading seen file: {e}")
        return set()


def save_seen(urls):
    """Save set of seen URLs to SEEN_FILE. urls: set or list of strings."""
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving seen file: {e}")
        return False


# =============================================================================
# NOTIFY
# =============================================================================


def notify(entry):
    """
    Send a notification for one new listing.
    Prefer Telegram if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set; else print to console.
    """
    title = entry.get("title", "N/A")
    link = entry.get("link", "N/A")
    published = entry.get("published") or "N/A"

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        msg = f"🚗 New listing\n\nTitle: {title}\nDate: {published}\nLink: {link}"
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(
                api_url,
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=10,
            )
            r.raise_for_status()
            return
        except requests.RequestException as e:
            print(f"Telegram send failed: {e}; falling back to console")

    print(f"[New] {title} | {published} | {link}")


# =============================================================================
# MAIN
# =============================================================================
#
# GitHub Actions (every 30 minutes):
# - Checkout repo, set up Python 3.11, install deps: pip install -r requirements.txt
# - Set env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (secrets)
# - Run: python rss_monitor.py
# - Commit and push SEEN_FILE (e.g. seen_rss.json) if changed, so state persists.
#


def main():
    """Fetch feed, detect new listings, notify, update seen list. Idempotent."""
    print(f"[{datetime.now()}] Starting RSS monitor...")

    seen = load_seen()
    print(f"Loaded {len(seen)} seen URLs")

    entries = fetch_feed(RSS_FEED_URL)
    if not entries:
        print("No entries fetched; exiting")
        return

    print(f"Fetched {len(entries)} entries")

    new_entries = [e for e in entries if e.get("link") and e["link"] not in seen]
    print(f"New listings: {len(new_entries)}")

    for entry in new_entries:
        notify(entry)
        seen.add(entry["link"])

    if new_entries:
        save_seen(seen)
        print("Updated seen list")
    else:
        print("No new listings; seen list unchanged")

    print(f"[{datetime.now()}] RSS monitor completed")


if __name__ == "__main__":
    main()
