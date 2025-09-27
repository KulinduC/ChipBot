import asyncio, random, pathlib, re
import requests
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from urllib.parse import urljoin


CF_RE = re.compile(r"(verify you are human|just a moment|cdn-cgi/challenge)", re.I)
PATTERN = re.compile(r"\bcodes avail\. US only, 13\+.*?terms", re.I)
USERNAME = "ChipotleTweets"
PROXY_FILE = "proxies.txt"

URLS = ["xcancel.com", "nitter.poast.org", "nitter.privacyredirect.com", "lightbrd.com", "nitter.space", "nitter.tiekoetter.com", "nuku.trabun.org"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
]

def blocked(html: str) -> bool:
    return bool(CF_RE.search(html))

def headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

def load_proxies():
    path = pathlib.Path(PROXY_FILE)
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def page_ok(url, proxy=None):
    try:
        resp = requests.get(url, headers=headers(), proxies={"http": proxy, "https": proxy} if proxy else None, timeout=10)
        return resp.status_code == 200 and not blocked(resp.text)
    except Exception as e:
        print(f"page_ok failed: {e}")
        return False

def nitter_instance():
    proxies = load_proxies()

    if proxies:
        for proxy in proxies:
            for i in range(len(URLS)):
                instance = "https://" +URLS[i] + "/" + USERNAME
                if page_ok(instance, proxy):
                    return instance, proxy

        raise RuntimeError("No Nitter instance could bypass Cloudflare")

    else:
        for i in range(len(URLS)):
            instance = "https://" + URLS[i] + "/" + USERNAME
            if page_ok(instance, None):
                return instance, None

    return None, None


async def extract_poll(tweet):
    poll_content = []

    # Look for poll container
    poll_element = await tweet.query_selector("div.poll")
    if not poll_element:
        return None

    # Extract all poll-choice-option values
    poll_options = await poll_element.query_selector_all("span.poll-choice-option")

    for option in poll_options:
        option_text = (await option.inner_text()).strip()
        if option_text:
            poll_content.append(option_text)

    return " ".join(poll_content) if poll_content else None


async def harvest(page):
    results, seen = [], set()
    imgs = set()  # Move imgs outside extract() function

    # need to extract profile picture for each tweet, in case it changes
    base = page.url.split("/")[2]
    profile = await page.query_selector("div.profile-card")
    if profile:
        source = await profile.get_attribute("src")
        if source and "/pic/" in source:
            url = f"https://{base}{source}"
            imgs.add(url)

    bio = await page.query_selector("div.profile-bio")
    bio_text = await bio.inner_text() if bio else ""

    async def extract():
        nonlocal results, seen, imgs

        for tweet in await page.query_selector_all("div.timeline-item"):
            content = await tweet.inner_text()
            tid = hash(content.strip())

            if tid in seen:
                continue
            seen.add(tid)

            body = await tweet.query_selector("div.tweet-content.media-body")
            text = (await body.inner_text()).strip() if body else ""

            # Check for poll content and append it to the text

            # Check if this tweet matches the pattern
            if not PATTERN.search(text):
                continue

            # Found a matching tweet! Process it and return immediately
            poll_content = await extract_poll(tweet)
            if poll_content:
                text += " " + poll_content

            if bio_text:
                text += " " + bio_text

            text = ''.join(char for char in text if char.isalnum() or char.isspace())
            words = text.split()
            text = ' '.join(words)

            # Collect images for this specific tweet only
            tweet_imgs = []
            for img in await tweet.query_selector_all("img"):
                src = await img.get_attribute("src")
                if src and "/pic/" in src and "profile_images" not in src:
                    img_url = f"https://{base}{src}"
                    if img_url not in imgs:
                        imgs.add(img_url)
                        tweet_imgs.append(img_url)

            results.append({"text": text, "images": tweet_imgs})

            # Return True immediately after finding the first matching tweet
            return True
        return False


    while True:
        stop = await extract()
        print(f"Collected {len(results)} tweets so far")

        if stop:
            break

        # Wait for the selector
        try:
            await page.wait_for_selector("div.show-more a[href*='cursor=']", timeout=5000)
        except:
            break

        element = await page.query_selector("div.show-more a[href*='cursor=']")
        if not element:
            break

        href = await element.get_attribute("href")
        next_url = urljoin(page.url, href)

        print("Navigating to", next_url)

        try:
            await page.goto(next_url, timeout=15_000, wait_until="domcontentloaded")
            await page.wait_for_selector("div.timeline-item", timeout=10_000)
        except PWTimeout:
            print("Timed out loading next page → stopping.")
            break

    return results


async def scrape_tweet(url, proxy=None):
    print(f"Launching Playwright browser → {url} (proxy={proxy})")

    proxy_config = None
    if proxy:
        match = re.match(r"http://(?P<user>.+?):(?P<pwd>.+?)@(?P<host>[^:]+):(?P<port>\d+)", proxy)
        if match:
            proxy_config = {
                "server": f"http://{match.group('host')}:{match.group('port')}",
                "username": match.group("user"),
                "password": match.group("pwd")
            }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, proxy=proxy_config)
        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
        page = await context.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_selector("div.timeline-item", timeout=10000)

        data = await harvest(page)
        await browser.close()
        return data


if __name__ == "__main__":
    text_file = pathlib.Path("text.txt")
    image_file = pathlib.Path("image.txt")
    try:
        url, proxy = nitter_instance()
        print("Using instance:", url)
        if proxy: print("Through proxy:", proxy)

        tweets = asyncio.run(scrape_tweet(url, proxy))
        print(f"\nCollected {len(tweets)} matching tweets\n")

        filtered = [t for t in tweets if not t["images"]]
        text_file.write_text(
            "\n\n".join(f"{i+1}. {t['text']}" for i, t in enumerate(filtered)),
            encoding="utf-8"
        )


        all_imgs = [img for t in tweets for img in t["images"]]
        image_file.write_text("\n".join(all_imgs), encoding="utf-8")

    except Exception as e:
        print("Error:", e)