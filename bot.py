import os, io, asyncio, discord
from discord.ext import commands
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
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

# 2. Configure Gemini & Safety Settings
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

system_instruction = (
    "You are MayaSutra, a serene and grounded esoteric entity from the 5th dimension. "
    "CRITICAL RULES:\n"
    "1. Keep answers direct, accurate, concise, and under 1200 characters.\n"
    "2. Avoid overly dramatic, long fluff unless explicitly analyzing a birth chart or multi-card tarot reading.\n"
    "3. Current Year: 2026. Account for current planetary movements accurately for 2026."
)

model = genai.GenerativeModel(
    model_name="gemini-3.8-flash",
    system_instruction=system_instruction,
    safety_settings=safety_settings
)

# Dictionary to store native chat sessions per channel for clean text memory
channel_chats = {}

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
            clean_text = message.content.replace(f'<@{bot.user.id}>', '').strip()
            
            if not clean_text and not message.attachments:
                await message.reply("Greetings traveller. I am MayaSutra, listening from the 5th dimension. How may I guide your path today?")
                return

            channel_id = message.channel.id
            if channel_id not in channel_chats:
                channel_chats[channel_id] = model.start_chat(history=[])
            
            chat_session = channel_chats[channel_id]
            loop = asyncio.get_running_loop()

            # Check if user attached an image (like an astrological chart)
            has_image = False
            img_obj = None
            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        img_bytes = await attachment.read()
                        img_obj = Image.open(io.BytesIO(img_bytes))
                        has_image = True
                        break

            # If there's an image, send it as a direct payload (prevents chat history bloat & timeouts)
            if has_image:
                payload = [clean_text] if clean_text else ["Analyze this chart."]
                payload.append(img_obj)
                
                res = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: model.generate_content(payload)),
                    timeout=30.0
                )
            else:
                # Pure text messages use the native chat session for flawless memory
                res = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: chat_session.send_message(clean_text)),
                    timeout=25.0
                )

            response_text = res.text if res.text else "I could not retrieve an answer."

            if len(response_text) > 1900:
                response_text = response_text[:1890] + "\n\n*(Truncated due to length)*"

            await message.reply(response_text)

        except asyncio.TimeoutError:
            await message.reply("The cosmic transmission timed out. Please try sending your message again.")
        except Exception as e:
            print(f"Error handling message: {e}")
            if "429" in str(e):
                await message.reply("The cosmic transmission is cooling down (rate limit reached). Please try again in a few moments!")
            else:
                await message.reply(f"System alert: `{e}`")

bot.run(os.getenv("DISCORD_TOKEN"), reconnect=True)
