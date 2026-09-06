import os, io, asyncio, discord
from discord.ext import commands
import google.generativeai as genai
from PIL import Image
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Dummy Web Server to satisfy Render Web Service port check
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MayaSutra is active.")

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), SimpleHTTPRequestHandler)
    server.serve_forever()

threading.Thread(target=run_http_server, daemon=True).start()

# Discord Bot Setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction="You are MayaSutra, a 5th-dimensional entity. Read fate, astrology, charts, tantra, and occult energies with a serene, atmospheric tone."
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
