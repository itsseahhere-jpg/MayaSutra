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

# AUTOMATIC MODEL DISCOVERY: Queries your API key live to find a working model name
def get_supported_model():
    try:
        print("Scanning available models for your API key...")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"Found supported model: {m.name}")
                if 'flash' in m.name.lower():
                    return m.name
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                return m.name
    except Exception as e:
        print(f"Model scan error: {e}")
    return "gemini-pro"

SELECTED_MODEL = get_supported_model()
print(f"Successfully locked onto model: {SELECTED_MODEL}")

model = genai.GenerativeModel(
    model_name=SELECTED_MODEL,
    system_instruction=system_instruction,
    safety_settings=safety_settings
)

channel_histories = {}
active_channels = set()

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

    channel_id = message.channel.id
    if channel_id in active_channels:
        return

    active_channels.add(channel_id)
    try:
        async with message.channel.typing():
            clean_text = str(message.content.replace(f'<@{bot.user.id}>', '').strip())
            
            if not clean_text and not message.attachments:
                await message.reply("Greetings traveller. I am MayaSutra, listening from the 5th dimension. How may I guide your path today?")
                return

            if channel_id not in channel_histories:
                channel_histories[channel_id] = []

            history_snippets = channel_histories[channel_id]
            context_block = "\n".join(history_snippets)
            
            prompt_content = []
            if context_block:
                prompt_content.append(f"Recent conversation context:\n{context_block}\n\nUser: {clean_text}")
            else:
                prompt_content.append(clean_text if clean_text else "Hello")

            if message.attachments:
                for attachment in message.attachments:
                    if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                        img_bytes = await attachment.read()
                        prompt_content.append(Image.open(io.BytesIO(img_bytes)))
                        break

            loop = asyncio.get_running_loop()
            res = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: model.generate_content(prompt_content)),
                timeout=20.0
            )

            response_text = res.text if res.text else "I could not retrieve an answer."

            if len(response_text) > 1900:
                response_text = response_text[:1890] + "\n\n*(Truncated due to length)*"

            channel_histories[channel_id].append(f"User: {clean_text}")
            channel_histories[channel_id].append(f"MayaSutra: {response_text}")
            if len(channel_histories[channel_id]) > 4:
                channel_histories[channel_id] = channel_histories[channel_id][-4:]

            await message.reply(response_text)

    except asyncio.TimeoutError:
        await message.reply("The cosmic transmission timed out. Please try sending your message again.")
    except Exception as e:
        print(f"Error handling message: {e}")
        if "429" in str(e):
            if channel_id in channel_histories:
                channel_histories[channel_id] = []
            await message.reply("The cosmic transmission hit a rate threshold and cleared its cache. Try your message again now!")
        else:
            await message.reply(f"System alert: `{e}`")
    finally:
        active_channels.discard(channel_id)

bot.run(os.getenv("DISCORD_TOKEN"), reconnect=True)
