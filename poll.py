import asyncio, aiohttp, xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import os
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()
PATTERN = re.compile(r"\bcodes avail\. US only, 13\+.*?terms", re.I)
USERNAME = "smurfingarg"
BASE     = "http://127.0.0.1:8081"
URL = f"{BASE}/{USERNAME}"

endpoint = "https://models.github.ai/inference"
model = "meta/Llama-4-Scout-17B-16E-Instruct"
token = os.environ["GITHUB_TOKEN"]

client = ChatCompletionsClient(
    endpoint=endpoint,
    credential=AzureKeyCredential(token),
)

last_id = None

def abs_url(u: str) -> str:
    if not u: return ""
    if u.startswith("http://") or u.startswith("https://"): return u
    return f"{BASE}{u}"


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
  description = item.findtext("description") or ""

  soup = BeautifulSoup(description, "html.parser")
  text = soup.get_text(" ", strip=True)
  images = [abs_url(img.get("src")) for img in soup.find_all("img") if img.get("src")]

  if profile_img:
    images.append(abs_url(profile_img))

  poll_options = [opt.get_text(strip=True) for opt in soup.select("span.poll-choice-option")]
  poll = " ".join(poll_options) if poll_options else None

  text += " " + poll if poll else ""

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


  return {"id": tweet_id, "text": text, "images": images}


async def poll():
  global last_id
  async with aiohttp.ClientSession() as session:
    while True:
        try:
          async with session.get(URL + "/rss") as resp:
            resp.raise_for_status()
            xml = await resp.text()
            entry = await parse(xml, session)
            if not entry:
              await asyncio.sleep(5); continue
            if entry["id"] == last_id:
              await asyncio.sleep(5); continue

            last_id = entry["id"]
            text = entry["text"]
            images = entry["images"]

            print("NEW TWEET:", text)
            print("IMAGES:", images)

        except Exception as e:
            print("Error:", e)
        await asyncio.sleep(5)

if __name__ == "__main__":
  asyncio.run(poll())