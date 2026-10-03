import os, io, asyncio, discord
from discord.ext import commands
import google.generativeai as genai
from PIL import Image
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

# 1. Health check server for Render
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

# 2. Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

system_instruction = (
    "You are MayaSutra, a serene and grounded esoteric entity from the 5th dimension. "
    "CRITICAL RULES:\n"
    "1. Keep answers direct, accurate, concise, and under 1200 characters.\n"
    "2. Avoid overly dramatic, long fluff unless explicitly analyzing a birth chart or multi-card tarot reading.\n"
    "3. Current Year: 2026. Account for current planetary movements accurately for 2026."
)

# Active production model
model = genai.GenerativeModel(
    model_name="gemini-3.8-flash",
    system_instruction=system_instruction
)


# 3. Discord Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in and online as {bot.user.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user or not bot.user.mentioned_in(message):
        return

    async with message.channel.typing():
        try:
            # Clean up mentions
            clean_text = message.content.replace(f'<@{bot.user.id}>', '').strip()
            
            # If user tagged without adding real text or an image
            if not clean_text and not message.attachments:
                await message.reply("Greetings traveller. I am MayaSutra, listening from the 5th dimension. How may I guide your path today?")
                return

            contents = []
            if clean_text:
                contents.append(clean_text)

            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        img_bytes = await attachment.read()
                        contents.append(Image.open(io.BytesIO(img_bytes)))
                        break

            # Fallback check to ensure payload is never empty
            if not contents:
                contents = ["Hello"]

            # Execute Gemini API call safely using get_running_loop
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(None, lambda: model.generate_content(contents))

            response_text = res.text if res.text else "I could not retrieve an answer."

            if len(response_text) > 1900:
                response_text = response_text[:1890] + "\n\n*(Truncated due to length)*"

            await message.reply(response_text)

        except Exception as e:
            print(f"Error handling message: {e}")
            if "429" in str(e):
                await message.reply("The cosmic transmission is cooling down (rate limit reached). Please try again in a few moments!")
            else:
                await message.reply(f"System alert: `{e}`")

bot.run(os.getenv("DISCORD_TOKEN"), reconnect=True)
