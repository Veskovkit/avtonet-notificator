# Avto.net Notifier

Python scraper that monitors avto.net for new car listings matching your criteria and sends Telegram notifications.

## Setup Instructions

### 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow the prompts to name your bot
4. Copy the bot token (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Your Telegram Chat ID

1. Search for `@userinfobot` on Telegram
2. Start a conversation with it
3. It will reply with your chat ID (a number like `123456789`)

### 3. Configure GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add two secrets:
   - `TELEGRAM_BOT_TOKEN`: Your bot token from step 1
   - `TELEGRAM_CHAT_ID`: Your chat ID from step 2

### 4. Configure Search Criteria

Edit `scraper.py` and modify the configuration section at the top:

```python
# Search URL from avto.net (modify query parameters as needed)
SEARCH_URL = "https://www.avto.net/rezultati.asp?..."

# Filter criteria
FILTER_BRAND = "BMW"      # e.g., "BMW", "Audi", "" for any
FILTER_MODEL = "320"      # e.g., "320", "A4", "" for any
FILTER_YEAR_MIN = 2018    # Minimum year (0 = no minimum)
FILTER_YEAR_MAX = 2023    # Maximum year (0 = no maximum)
```

**To get the search URL:**
1. Go to [avto.net](https://www.avto.net)
2. Use the search filters to set your criteria
3. Copy the URL from your browser's address bar
4. Paste it into `SEARCH_URL` in `scraper.py`

### 5. Enable GitHub Actions

1. Push the code to your GitHub repository
2. Go to **Actions** tab in your repository
3. The workflow will run automatically every 30 minutes
4. You can also trigger it manually via **Actions** → **Check Avto.net Listings** → **Run workflow**

## How It Works

1. The scraper fetches the search results page from avto.net
2. Extracts listing details (title, year, price, link)
3. Filters listings based on your criteria
4. Compares against previously seen listings in `seen_ads.json`
5. Sends Telegram notifications for new listings
6. Updates `seen_ads.json` with new listing IDs
7. GitHub Actions commits the updated file back to the repository

## Files

- `scraper.py` - Main scraper script
- `seen_ads.json` - Tracks which listings have been seen
- `.github/workflows/check_avto.yml` - GitHub Actions workflow
- `requirements.txt` - Python dependencies
