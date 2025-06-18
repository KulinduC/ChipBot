import time, random, pathlib, re, warnings
import requests, undetected_chromedriver as uc
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


warnings.filterwarnings("ignore", category=UserWarning)

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

    def twiiit_redirect(proxy=None):
        try:
            resp = requests.get(
                URL,
                headers=get_random_headers(),
                allow_redirects=False,
                proxies={"http": proxy, "https": proxy} if proxy else None,
                timeout=10
            )
            return resp.headers.get("Location")
        except Exception as e:
            print(f"twiiit_redirect failed: {e}")
            return None

    def page_ok(u, proxy=None):
        try:
            resp = requests.get(
                u,
                headers=get_random_headers(),
                proxies={"http": proxy, "https": proxy} if proxy else None,
                timeout=10
            )
            return resp.status_code == 200 and not blocked_by_cloudflare(resp.text)
        except Exception as e:
            print(f"page_ok failed: {e}")
            return False

    tried = set()
    for proxy in proxies:
        tried.clear()
        for _ in range(inst_max):
            inst = twiiit_redirect(proxy)
            if not inst or inst in tried:
                continue
            tried.add(inst)
            if page_ok(inst, proxy):
                return inst, proxy
            if len(tried) >= inst_max:
                break

    raise RuntimeError("No Nitter instance could bypass Cloudflare")

def scrape_tweet(url, proxy=None):
    print(f"Launching headless browser → {url} (proxy={proxy})")

    options = uc.ChromeOptions()
    options.add_argument("--disable-gpu")
    #options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1280,800")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-infobars")

    seleniumwire_options = {
        "proxy": {
            "http": proxy,
            "https": proxy,
            "no_proxy": "localhost,127.0.0.1"
        }
    }

    driver = webdriver.Chrome(options=options, seleniumwire_options=seleniumwire_options)
    try:
        driver.get(url)
        time.sleep(5)

        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.timeline-item"))
        )
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

        tweet_text = tweet.find_element(By.CSS_SELECTOR, "div.tweet-content.media-body").text.strip()

        images = []
        for img in tweet.find_elements(By.CSS_SELECTOR, "img"):
            src = img.get_attribute("src")
            if src and "/pic/" in src and "profile_images" not in src:
                images.append(src)

        return {"text": tweet_text, "images": images}

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        url, px = nitter_instance()
        tw = scrape_tweet(url, proxy=px)
        print("\nLATEST TWEET:\n")
        print(tw["text"])
        if tw["images"]:
            print(tw["images"])
        else:
            print("No images")
    except Exception as e:
        print(f"Error: {e}")