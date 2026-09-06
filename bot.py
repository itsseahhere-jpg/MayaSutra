import os, io, discord
from discord.ext import commands
import google.generativeai as genai
from PIL import Image

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction="You are MayaSutra, a 5th-dimensional entity. Read fate, astrology, charts, tantra, and occult energies with a serene, atmospheric, and deeply insightful tone."
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_message(message):
    if message.author == bot.user or not bot.user.mentioned_in(message):
        return
    
    async with message.channel.typing():
        text = message.content.replace(f'<@{bot.user.id}>', '').strip()
        contents = [text or "Interpret this chart or image through the 5th dimensional lens."]
        
        if message.attachments:
            img_bytes = await message.attachments[0].read()
            contents.append(Image.open(io.BytesIO(img_bytes)))
            
        res = model.generate_content(contents)
        await message.reply(res.text)

bot.run(os.getenv("DISCORD_TOKEN"))
        
