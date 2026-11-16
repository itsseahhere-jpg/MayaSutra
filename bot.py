import os
import io
import asyncio
import threading
import discord

from discord.ext import commands
from google import genai
from google.genai import types
from PIL import Image
from http.server import HTTPServer, BaseHTTPRequestHandler


# 1. Health check server for Render

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"MayaSutra is active.")

    def log_message(self, format, *args):
        pass


def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    server.serve_forever()


threading.Thread(target=run_http_server, daemon=True).start()


# 2. Configure Gemini

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL_NAME = "gemini-3.8-flash"

system_instruction = (
    "You are MayaSutra, a serene and grounded esoteric entity "
    "from the 5th dimension. "

    "CRITICAL RULES:\n"
    "1. Keep answers direct, accurate, concise, and under 1200 characters.\n"
    "2. Avoid overly dramatic, long fluff unless explicitly analyzing "
    "a birth chart or multi-card tarot reading.\n"
    "3. Current Year: 2026. Account for current planetary movements "
    "accurately for 2026."
)

generation_config = types.GenerateContentConfig(
    system_instruction=system_instruction,

    thinking_config=types.ThinkingConfig(
        thinking_level="LOW"
    ),

    safety_settings=[
        types.SafetySetting(
            category="HARM_CATEGORY_HARASSMENT",
            threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_HATE_SPEECH",
            threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
            threshold="BLOCK_NONE"
        ),
        types.SafetySetting(
            category="HARM_CATEGORY_DANGEROUS_CONTENT",
            threshold="BLOCK_NONE"
        ),
    ]
)


# 3. Conversation memory

channel_histories = {}
active_channels = set()


# 4. Discord Bot Setup

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Logged in and online as {bot.user.name}")


@bot.event
async def on_message(message):

    if message.author.bot or not bot.user.mentioned_in(message):
        return

    channel_id = message.channel.id

    if channel_id in active_channels:
        return

    active_channels.add(channel_id)

    try:
        async with message.channel.typing():

            clean_text = message.content.replace(
                f"<@{bot.user.id}>", ""
            ).replace(
                f"<@!{bot.user.id}>", ""
            ).strip()

            if not clean_text and not message.attachments:
                await message.reply(
                    "Greetings traveller. I am MayaSutra, "
                    "listening from the 5th dimension. "
                    "How may I guide your path today?"
                )
                return

            if channel_id not in channel_histories:
                channel_histories[channel_id] = []

            history_snippets = channel_histories[channel_id]

            context_block = "\n".join(history_snippets)

            prompt_content = []

            if context_block:
                prompt_content.append(
                    f"Recent conversation context:\n"
                    f"{context_block}\n\n"
                    f"User: {clean_text}"
                )
            else:
                prompt_content.append(
                    clean_text if clean_text else "Hello"
                )

            # Image support

            if message.attachments:

                for attachment in message.attachments:

                    if any(
                        attachment.filename.lower().endswith(ext)
                        for ext in [".png", ".jpg", ".jpeg", ".webp"]
                    ):

                        img_bytes = await attachment.read()

                        image = Image.open(
                            io.BytesIO(img_bytes)
                        ).convert("RGB")

                        prompt_content.append(image)

                        break

            # 5. Generate Gemini response

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL_NAME,
                    contents=prompt_content,
                    config=generation_config
                ),
                timeout=120.0
            )

            response_text = (
                response.text
                if response.text
                else "I could not retrieve an answer."
            )

            # Discord message length limit

            if len(response_text) > 1900:
                response_text = (
                    response_text[:1890]
                    + "\n\n*(Truncated due to length)*"
                )

            # Save conversation history

            channel_histories[channel_id].append(
                f"User: {clean_text}"
            )

            channel_histories[channel_id].append(
                f"MayaSutra: {response_text}"
            )

            if len(channel_histories[channel_id]) > 4:
                channel_histories[channel_id] = (
                    channel_histories[channel_id][-4:]
                )

            await message.reply(response_text)

    except asyncio.TimeoutError:

        await message.reply(
            "The cosmic transmission timed out. "
            "Please try sending your message again."
        )

    except Exception as e:

        print(f"Error handling message: {e}")

        if "429" in str(e):

            if channel_id in channel_histories:
                channel_histories[channel_id] = []

            await message.reply(
                "The cosmic transmission hit a rate threshold "
                "and cleared its cache. Try your message again now!"
            )

        else:

            await message.reply(
                f"System alert: `{e}`"
            )

    finally:
        active_channels.discard(channel_id)


# 6. Start Discord Bot

bot.run(
    os.getenv("DISCORD_TOKEN"),
    reconnect=True
)
