import os, io, discord
from discord.ext import commands
import google.generativeai as genai
from PIL import Image
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# Web server for Render health check
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

# Setup Gemini with character limit in system instructions
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    model_name="gemini-3.6-flash",
    system_instruction=(
        "You are MayaSutra, a 5th-dimensional entity. Read fate, astrology, charts, tantra, "
        "and occult energies with a serene, atmospheric tone. Keep your responses complete, "
        "insightful, and strictly under 1800 characters."
    )
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_message(message):
    if message.author == bot.user or not bot.user.mentioned_in(message):
        return
    
    async with message.channel.typing():
        try:
            text = message.content.replace(f'<@{bot.user.id}>', '').strip()
            contents = [text or "Interpret this chart or image through the 5th dimensional lens."]
            
            if message.attachments:
                img_bytes = await message.attachments[0].read()
                contents.append(Image.open(io.BytesIO(img_bytes)))
                
            res = await model.generate_content_async(contents)
            response_text = res.text

            # Enforce Discord's 2000 character limit
            if len(response_text) > 1900:
                response_text = response_text[:1890] + "\n\n*(Truncated to fit Discord length limits)*"

            await message.reply(response_text)
        except Exception as e:
            await message.reply(f"The ethereal currents are disrupted: `{e}`")

bot.run(os.getenv("DISCORD_TOKEN"))
