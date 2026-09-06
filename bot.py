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

# Setup Gemini with grounded, clear instructions
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

system_instruction = (
    "You are MayaSutra, an astrological and occult entity. "
    "CRITICAL RULES:\n"
    "1. TONE: Be direct, concise, and accurate. Avoid overly dramatic, wordy fluff unless analyzing a complex chart or tarot spread.\n"
    "2. ACCURACY: Always check real-time planetary positions for the current date (2026). Do not hallucinate old transits from 2024 or 2025.\n"
    "3. LENGTH: Keep general answers under 1000 characters."
)

model = genai.GenerativeModel(
    model_name="gemini-3.6-flash",
    system_instruction=system_instruction
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
            contents = [text or "Interpret this image through an esoteric lens."]
            
            if message.attachments:
                img_bytes = await message.attachments[0].read()
                contents.append(Image.open(io.BytesIO(img_bytes)))
                
            res = await model.generate_content_async(contents)
            response_text = res.text

            if len(response_text) > 1900:
                response_text = response_text[:1890] + "\n\n*(Truncated to fit length limit)*"

            await message.reply(response_text)
        except Exception as e:
            await message.reply(f"Error processing request: `{e}`")

bot.run(os.getenv("DISCORD_TOKEN"))
