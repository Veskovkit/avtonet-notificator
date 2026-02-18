#!/usr/bin/env python3
"""
Avto.net scraper and Telegram notifier.
Scrapes search results, filters by criteria, and sends notifications for new listings.
"""

import json
import os
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ============================================================================
# CONFIGURATION - Modify these values to change search criteria
# ============================================================================

# Search URL from avto.net (modify query parameters as needed)
SEARCH_URL = "https://www.avto.net/results.asp?znamka=Hyundai&model=ix35&modelID=&tip=katerikoli%20tip&znamka2=&model2=&tip2=katerikoli%20tip&znamka3=&model3=&tip3=katerikoli%20tip&cenaMin=0&cenaMax=7000&letnikMin=2010&letnikMax=2090&bencin=0&starost2=999&oblika=0&ccmMin=0&ccmMax=99999&mocMin=&mocMax=&kmMin=0&kmMax=250000&kwMin=0&kwMax=999&motortakt=&motorvalji=&lokacija=0&sirina=&dolzina=&dolzinaMIN=&dolzinaMAX=&nosilnostMIN=&nosilnostMAX=&sedezevMIN=&sedezevMAX=&lezisc=&presek=&premer=&col=&vijakov=&EToznaka=&vozilo=&airbag=&barva=&barvaint=&doseg=&BkType=&BkOkvir=&BkOkvirType=&Bk4=&EQ1=1000000000&EQ2=1000000000&EQ3=1000000000&EQ4=100000000&EQ5=1000000000&EQ6=1000000000&EQ7=1000000120&EQ8=101000000&EQ9=100000002&EQ10=1000000000&KAT=1010000000&PIA=&PIAzero=&PIAOut=&PSLO=&akcija=&paketgarancije=&broker=&prikazkategorije=&kategorija=&ONLvid=&ONLnak=&zaloga=&arhiv=&presort=&tipsort=&stran="

# Filter criteria
FILTER_BRAND = ""  # Empty string = any brand
FILTER_MODEL = ""  # Empty string = any model
FILTER_YEAR_MIN = 0  # 0 = no minimum
FILTER_YEAR_MAX = 0  # 0 = no maximum

# State file
SEEN_ADS_FILE = "seen_ads.json"

# Telegram configuration (from environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ============================================================================
# SCRAPING FUNCTIONS
# ============================================================================


def get_page(url):
    """Fetch the search results page. Uses a session: hit homepage then car category so results.asp gets cookies and a plausible Referer (avto.net often returns 403 otherwise)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "sl-SI,sl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }
    try:
        session = requests.Session()
        session.headers.update(headers)
        session.get("https://www.avto.net/", timeout=15)
        session.get("https://www.avto.net/Ads/search_category.asp?SID=10000", timeout=15)
        session.headers["Referer"] = "https://www.avto.net/Ads/search_category.asp?SID=10000"
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching page: {e}")
        return None


def extract_listing_id(url):
    """Extract unique identifier from listing URL."""
    try:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if path_parts:
            return path_parts[-1]
        return url
    except Exception:
        return url


def parse_listing(listing_element):
    """Extract data from a single listing element."""
    try:
        listing = {}
        
        # Find title and link - try multiple selectors
        title_link = None
        if listing_element.name == "a":
            title_link = listing_element
        else:
            title_link = listing_element.find("a", class_="stretched-link")
            if not title_link:
                title_link = listing_element.find("a", href=lambda h: h and "/oglasi/" in h)
            if not title_link:
                title_link = listing_element.find("a")
        
        if not title_link:
            return None
        
        listing["title"] = title_link.get_text(strip=True)
        if not listing["title"]:
            return None
        
        href = title_link.get("href", "")
        if not href or "/oglasi/" not in href:
            return None
        
        listing["link"] = urljoin("https://www.avto.net/", href)
        listing["id"] = extract_listing_id(listing["link"])
        
        # Find year - try multiple patterns
        year = None
        year_elem = listing_element.find("span", string=lambda s: s and s and "Letnik" in str(s))
        if not year_elem:
            year_elem = listing_element.find(string=lambda s: s and "Letnik" in str(s))
        
        if year_elem:
            year_text = str(year_elem).strip()
            try:
                # Extract year from text like "Letnik: 2020" or "2020"
                parts = year_text.split()
                for part in reversed(parts):
                    if part.isdigit() and len(part) == 4:
                        year = int(part)
                        break
            except (ValueError, IndexError):
                pass
        
        listing["year"] = year
        
        # Find price - try multiple selectors
        price = "N/A"
        price_elem = listing_element.find("span", class_="cena")
        if not price_elem:
            price_elem = listing_element.find("div", class_="cena")
        if not price_elem:
            price_elem = listing_element.find(string=lambda s: s and "€" in str(s))
        
        if price_elem:
            if hasattr(price_elem, "get_text"):
                price = price_elem.get_text(strip=True)
            else:
                price = str(price_elem).strip()
        
        listing["price"] = price
        
        return listing
    except Exception as e:
        print(f"Error parsing listing: {e}")
        return None


def scrape_listings(html_content):
    """Parse HTML and extract all listings."""
    if not html_content:
        return []
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        listings = []
        
        # Try multiple selectors to find listing containers
        listing_elements = []
        
        # Common avto.net patterns
        listing_elements = soup.find_all("div", class_="GO-Results-Row")
        if not listing_elements:
            listing_elements = soup.find_all("div", class_="GO-Results-Row-Data")
        if not listing_elements:
            listing_elements = soup.find_all("div", {"data-id": True})
        if not listing_elements:
            listing_elements = soup.find_all("article")
        if not listing_elements:
            # Fallback: find all links that look like listing links
            all_links = soup.find_all("a", href=True)
            listing_elements = [link.parent for link in all_links if "/oglasi/" in link.get("href", "")]
        
        for elem in listing_elements:
            listing = parse_listing(elem)
            if listing and listing.get("id"):
                listings.append(listing)
        
        return listings
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return []


# ============================================================================
# FILTERING FUNCTIONS
# ============================================================================


def matches_criteria(listing):
    """Check if listing matches filter criteria."""
    if FILTER_BRAND and FILTER_BRAND.lower() not in listing.get("title", "").lower():
        return False
    
    if FILTER_MODEL and FILTER_MODEL.lower() not in listing.get("title", "").lower():
        return False
    
    year = listing.get("year")
    if year:
        if FILTER_YEAR_MIN > 0 and year < FILTER_YEAR_MIN:
            return False
        if FILTER_YEAR_MAX > 0 and year > FILTER_YEAR_MAX:
            return False
    
    return True


# ============================================================================
# STATE MANAGEMENT
# ============================================================================


def load_seen_ads():
    """Load seen ad IDs from JSON file."""
    if not os.path.exists(SEEN_ADS_FILE):
        return []
    
    try:
        with open(SEEN_ADS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "seen_ids" in data:
                return data["seen_ids"]
            return []
    except Exception as e:
        print(f"Error loading seen ads: {e}")
        return []


def save_seen_ads(seen_ids):
    """Save seen ad IDs to JSON file."""
    try:
        with open(SEEN_ADS_FILE, "w", encoding="utf-8") as f:
            json.dump(seen_ids, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving seen ads: {e}")
        return False


# ============================================================================
# NOTIFICATION FUNCTIONS
# ============================================================================


def send_telegram_message(listing):
    """Send Telegram notification for a listing."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not configured")
        return False
    
    message = f"🚗 New Listing Found!\n\n"
    message += f"Title: {listing.get('title', 'N/A')}\n"
    message += f"Year: {listing.get('year', 'N/A')}\n"
    message += f"Price: {listing.get('price', 'N/A')}\n"
    message += f"Link: {listing.get('link', 'N/A')}"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Error sending Telegram message: {e}")
        return False


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def main():
    """Main execution function."""
    print(f"[{datetime.now()}] Starting scraper...")
    
    # Load seen ads
    seen_ids = load_seen_ads()
    print(f"Loaded {len(seen_ids)} seen ad IDs")
    
    # Fetch page
    print(f"Fetching: {SEARCH_URL}")
    html_content = get_page(SEARCH_URL)
    if not html_content:
        print("Failed to fetch page (network/403); skipping this run")
        print(f"[{datetime.now()}] Scraper completed")
        return
    
    # Parse listings
    print("Parsing listings...")
    all_listings = scrape_listings(html_content)
    print(f"Found {len(all_listings)} listings")
    
    # Filter listings
    filtered_listings = [l for l in all_listings if matches_criteria(l)]
    print(f"Filtered to {len(filtered_listings)} matching listings")
    
    # Find new listings
    new_listings = [l for l in filtered_listings if l.get("id") not in seen_ids]
    print(f"Found {len(new_listings)} new listings")
    
    # Send notifications and update seen list
    updated = False
    for listing in new_listings:
        listing_id = listing.get("id")
        if listing_id:
            print(f"Sending notification for: {listing.get('title', 'Unknown')}")
            send_telegram_message(listing)
            seen_ids.append(listing_id)
            updated = True
    
    # Save updated seen list
    if updated:
        save_seen_ads(seen_ids)
        print("Updated seen_ads.json")
    else:
        print("No new listings, no update needed")
    
    print(f"[{datetime.now()}] Scraper completed")


if __name__ == "__main__":
    main()
