import asyncio, aiohttp, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import random
import os
from openai import OpenAI
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from dotenv import load_dotenv


PATTERN = re.compile(r"codes\s+avail\.?\s+US\s+only,\s*13\+", re.I)
USERNAME = "smurfingarg"

# Use local Nitter instance from environment variable
BASE = "http://localhost:8080"
URL = f"{BASE}/{USERNAME}"
FEED = f"{URL}/rss"
POLL_SEC = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13.5; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36"
]

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
last_id = None

def abs_url(u: str) -> str:
    nitter_base = "https://nitter.net"
    if not u: return ""
    if u.startswith("http://") or u.startswith("https://"): return u
    return f"{nitter_base}{u}"


async def parse(xml_text, session):
  root = ET.fromstring(xml_text)

  profile_img = ""
  channel_img = root.find("./channel/image/url")
  if channel_img is not None:
      profile_img = channel_img.text.strip()


  item = root.find("./channel/item")
  if item is None:
    return None

  tweet_id = item.findtext("guid") or ""
  link = item.findtext("link") or ""
  description = item.findtext("description") or ""

  soup = BeautifulSoup(description, "html.parser")
  text = soup.get_text(" ", strip=True)
  images = [abs_url(img.get("src")) for img in soup.find_all("img") if img.get("src")]

  if profile_img:
    images.append(abs_url(profile_img))

  async with session.get(URL) as resp:
      resp.raise_for_status()
      html = await resp.text()

      profile_soup = BeautifulSoup(html, "html.parser")
      bio = profile_soup.select_one("div.profile-bio")
      bio_text = bio.get_text(" ",strip=True) if bio else ""
      text += " " + bio_text if bio_text else ""

      banner = profile_soup.select_one("div.profile-banner img")
      banner_link = abs_url(banner.get("src")) if banner and banner.get("src") else ""

      if banner_link:
        images.append(banner_link)


  return {"id": tweet_id, "text": text, "link": link, "images": images}


async def poll(link):
    async with async_playwright() as p:
      browser = await p.chromium.launch(headless=True)
      context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
      page = await context.new_page()

    try:
      await page.goto(link, timeout=15000)
      await page.wait_for_selector("div.tweet-body", timeout=10000)

      poll_element = await page.query_selector("div.poll")
      if not poll_element:
        await browser.close()
        return ""

      poll_options = await poll_element.query_selector_all("span.poll-choice-option")
      poll_content = []

      for option in poll_options:
          option_text = (await option.inner_text()).strip()
          if option_text:
              poll_content.append(option_text)

      await browser.close()
      return " ".join(poll_content) if poll_content else ""
    except Exception as e:
      print(f"Error getting poll data: {e}")
      await browser.close()
      return ""

async def scrape(code_queue):
  global last_id
  async with aiohttp.ClientSession() as session:
    while True:
        try:
          async with session.get(FEED) as resp:
            resp.raise_for_status()
            xml = await resp.text()
            entry = await parse(xml, session)
            if not entry:
              await asyncio.sleep(POLL_SEC); continue
            if entry["id"] == last_id:
              await asyncio.sleep(POLL_SEC); continue

            last_id = entry["id"]
            link = entry["link"]
            text = entry["text"]
            images = entry["images"]

            if PATTERN.search(text):
              text += " " + await poll(link)
              text = "".join(char for char in text if char.isalnum() or char.isspace())
              filtered_text = " ".join(text.split())

              print(f"Filtered text: {filtered_text}")
              content = [
                {"type": "text", "text": f"Extract promotional codes from the text and/or images. Return ONLY the code(s) separated by commas if there are multiple. If no codes found, return 'None'. Text: {filtered_text}"}
              ]

              for img_url in images:
                if img_url:
                  content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url}
                  })

              response = client.responses.create(
                model="gpt-5-nano",
                messages=[{
                  "role": "user",
                  "content": content
                }],
              )
              await code_queue.put(response.output_text)


        except Exception as e:
            print("Error:", e)
        await asyncio.sleep(POLL_SEC)