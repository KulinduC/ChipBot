import time, random, pathlib, sys, re
import requests, undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup

USERNAME = "ChipotleTweets"
URL = f"https://twiiit.com/{USERNAME}"
PROXY_FILE = "proxies.txt"


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.2535.67",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
]

CF_RE = re.compile(r"(verify you are human|just a moment|cdn-cgi/challenge)", re.I)

def blocked_by_cloudflare(html: str) -> bool:
    return bool(CF_RE.search(html))


def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1"
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


def nitter_instance():
    proxies = load_proxies()
    inst_max = instance_count()
    print(f"Twiiit reports {inst_max} instances online")

    # helper to get redirect (optionally through proxy)
    def twiiit_redirect(proxy=None):
        resp = requests.get(URL, headers=get_random_headers(),
                            allow_redirects=False,
                            proxies=proxy, timeout=10)
        return resp.headers.get("Location")

    # helper to test an instance via requests
    def page_ok(u, proxy=None):
        r = requests.get(u, headers=get_random_headers(),
                         proxies=proxy, timeout=10)
        return (r.status_code == 200 and not blocked_by_cloudflare(r.text))


    tried = set()
    for _ in range(inst_max):
        inst = twiiit_redirect()
        if not inst or inst in tried:
            continue
        tried.add(inst)
        try:
            if page_ok(inst):
                return inst, None
        except Exception:
            pass
        if len(tried) >= inst_max:
            break

    for proxy in proxies:
        proxy_dict = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
        tried.clear()
        for _ in range(inst_max):
            inst = twiiit_redirect(proxy_dict)
            if not inst or inst in tried:
                continue
            tried.add(inst)
            try:
                if page_ok(inst, proxy_dict):
                    return inst, proxy
            except Exception:
                pass
            if len(tried) >= inst_max:
                break

    raise RuntimeError("No Nitter instance could bypass Cloudflare")


def scrape_tweet(url, proxy=None):
    host = url.split('/')[2]
    print(f"Launching headless browser → {url} (proxy={proxy})")

    opts = uc.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    if proxy:
        opts.add_argument(f"--proxy-server=http://{proxy}")

    driver = uc.Chrome(options=opts)
    try:
        driver.get(url)
        time.sleep(5)

        tweets = driver.find_elements(By.CSS_SELECTOR, "div.timeline-item")
        if not tweets:
            raise Exception("No tweets found")

        for t in tweets:
            if t.find_elements(By.CSS_SELECTOR, "div.pinned"):
                continue
            tweet = t
            break
        else:
            tweet = tweets[0]

        tweet_text = tweet.find_element(
            By.CSS_SELECTOR, "div.tweet-content.media-body").text.strip()

        images = []
        for a in tweet.find_elements(By.CSS_SELECTOR, "a.still-image"):
            href = a.get_attribute("href")
            if href and href.startswith("/pic/"):
                images.append(f"https://{host}{href}")

        return {"text": tweet_text, "images": images}

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    print(load_proxies())
    try:
        url, px = nitter_instance()
        tw   = scrape_tweet(url, proxy=px)
        print("\nLATEST TWEET:\n")
        print(tw["text"])
        print(tw["images"])
    except Exception as e:
        print(f"Error: {e}")