import asyncio, random, pathlib, re, warnings
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

warnings.filterwarnings("ignore", category=UserWarning)

USERNAME = "ChipotleTweets"
URL = f"https://twiiit.com/{USERNAME}"
PROXY_FILE = "proxies.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
]

CF_RE = re.compile(r"(verify you are human|just a moment|cdn-cgi/challenge)", re.I)

def blocked_by_cloudflare(html: str) -> bool:
    return bool(CF_RE.search(html))

def get_random_headers():
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

def instance_count() -> int:
    try:
        resp = requests.get("https://twiiit.com/", headers=get_random_headers(), timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        m = re.search(r"currently\s+(\d+)\s+instances", soup.get_text(" ", strip=True), re.I)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0

def get_redirect_instance(proxy=None):
    try:
        resp = requests.get(URL, headers=get_random_headers(), allow_redirects=False,
                            proxies={"http": proxy, "https": proxy} if proxy else None, timeout=10)
        return resp.headers.get("Location")
    except Exception as e:
        print(f"twiiit_redirect failed: {e}")
        return None

def page_ok(u, proxy=None):
    try:
        resp = requests.get(u, headers=get_random_headers(), proxies={"http": proxy, "https": proxy} if proxy else None, timeout=10)
        return resp.status_code == 200 and not blocked_by_cloudflare(resp.text)
    except Exception as e:
        print(f"page_ok failed: {e}")
        return False

def nitter_instance():
    proxies = load_proxies()
    inst_max = instance_count()
    print(f"Twiiit reports {inst_max} instances online")
    tried = set()

    for proxy in proxies:
        tried.clear()
        for _ in range(inst_max):
            inst = get_redirect_instance(proxy)
            if not inst or inst in tried:
                continue
            tried.add(inst)
            if page_ok(inst, proxy):
                return inst, proxy
            if len(tried) >= inst_max:
                break

    raise RuntimeError("No Nitter instance could bypass Cloudflare")


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
        try:
            await page.goto(url, timeout=15000)
            await page.wait_for_selector("div.timeline-item", timeout=10000)

            tweets = await page.query_selector_all("div.timeline-item")
            if not tweets:
                raise Exception("No tweets found")

            tweet = None
            for t in tweets:
                pinned = await t.query_selector("div.pinned")
                if not pinned:
                    tweet = t
                    break
            if not tweet:
                tweet = tweets[0]

            text_el = await tweet.query_selector("div.tweet-content.media-body")
            tweet_text = await text_el.inner_text() if text_el else ""

            images = []
            img_tags = await tweet.query_selector_all("img")
            for img in img_tags:
                src = await img.get_attribute("src")
                if src and "/pic/" in src and "profile_images" not in src:
                    images.append(src)

            await browser.close()
            return {"text": tweet_text.strip(), "images": images}

        finally:
            await browser.close()


if __name__ == "__main__":
    try:
        url, px = nitter_instance()
        tweet = asyncio.run(scrape_tweet(url, proxy=px))
        print("\nLATEST TWEET:\n")
        print(tweet["text"])
        if tweet["images"]:
            print(tweet["images"])
        else:
            print("No images")
    except Exception as e:
        print(f"Error: {e}")