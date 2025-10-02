import discord
from dotenv import load_dotenv
import os
import asyncio
from scrape import scrape

code_queue = asyncio.Queue()


class ChipBot(discord.Client):
  def __init__(self):
    intents = discord.Intents.all()
    intents.message_content = True
    super().__init__(intents=intents)

  async def on_ready(self):
    print(f'{self.user} has connected to Discord!')
    asyncio.create_task(self.send_codes())
    asyncio.create_task(scrape(code_queue))

  async def on_message(self, message):
    if message.author == self.user:
        return

    if message.content.startswith('!ping'):
        await message.channel.send('Pong!')

  async def send_codes(self):
    await self.wait_until_ready()
    channel = discord.utils.get(self.get_all_channels(), name="chip-monitor")
    if not channel:
      print("Could not find 'chip-monitor' channel")
      return

    print(f"Bot ready to send codes to #{channel.name}")

    while True:
        codes = await code_queue.get()
        codes = [c.strip() for c in codes.split(',')]
        if channel:
          for code in codes:
            await channel.send(f"sms://888222/;?&body={code}")


if __name__ == "__main__":
  load_dotenv()
  TOKEN = os.getenv("DISCORD_TOKEN")
  bot = ChipBot()
  bot.run(TOKEN)