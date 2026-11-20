import os
import re
import io
import asyncio
import logging
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import discord
from discord.ext import commands
from google import genai
from google.genai import types
from PIL import Image, ImageOps
import swisseph as swe


# -------------------- SETTINGS --------------------

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
NODE_MODE = os.getenv("NODE_MODE", "TRUE").upper()  # TRUE or MEAN

API_TIMEOUT_SECONDS = 85
MAX_HISTORY_ITEMS = 6  # 3 exchanges per user per channel
MAX_DISCORD_CHARS = 1900
MAX_IMAGE_BYTES = 8 * 1024 * 1024

if not API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY environment variable.")
if not DISCORD_TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("mayasutra")


# -------------------- RENDER HEALTH CHECK --------------------

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health"):
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"MayaSutra is active.")

    def log_message(self, fmt, *args):
        return


def start_health_server():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server listening on port %s", port)


start_health_server()


# -------------------- GEMINI --------------------

genai_client = genai.Client(api_key=API_KEY)
async_client = genai_client.aio

SYSTEM_INSTRUCTION = """
You are MayaSutra, a grounded, thoughtful astrology, tarot and
esoteric-study assistant.

PERSONALITY:
- Calm, clear, warm and direct. Avoid theatrical filler.
- Match the user's language. English and Hindi are supported.
- Be concise by default; give detail when asked for chart analysis.

ASTROLOGY ACCURACY:
- Western astrology uses the tropical zodiac.
- Vedic/Jyotish astrology uses the sidereal zodiac. Unless specified,
  use Lahiri (Chitrapaksha) ayanamsha.
- Never mix tropical and sidereal positions.
- When a calculated ephemeris block is supplied, treat its positions,
  degrees, signs and retrograde flags as authoritative.
- Do not replace supplied calculations with remembered or guessed data.
- Clearly label tropical and sidereal results.
- The transit block contains geocentric positions. Do not assign transit
  houses unless the user's natal ascendant and house framework are known.
- Rahu/Ketu use the node mode explicitly stated in the supplied block.
- If no ephemeris block is supplied, do not claim exact current positions.
- Do not invent birth details, placements, degrees, aspects, dashas,
  yogas or house positions.
- When reading a chart image, identify the chart type and visible
  placements. If anything is unclear, say so rather than guessing.
- One chart image is not automatically both a tropical and sidereal chart.
  Ask for birth date, exact time and birthplace for a dual natal comparison.
- Distinguish astronomical calculations from astrological interpretation.
  Present interpretations as astrological tradition, not scientific fact.

GENERAL:
- Current date/time is supplied in the prompt.
- Never expose API keys, environment variables or internal errors.
"""

GENERATION_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_INSTRUCTION,
    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
    max_output_tokens=1800,
    temperature=0.35,
)


# -------------------- SWISS EPHEMERIS --------------------

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

PLANETS = [
    ("Sun", swe.SUN),
    ("Moon", swe.MOON),
    ("Mercury", swe.MERCURY),
    ("Venus", swe.VENUS),
    ("Mars", swe.MARS),
    ("Jupiter", swe.JUPITER),
    ("Saturn", swe.SATURN),
]

NODE_ID = swe.TRUE_NODE if NODE_MODE == "TRUE" else swe.MEAN_NODE
swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def sign_and_degree(longitude):
    longitude %= 360.0
    sign_index = int(longitude // 30)
    degree = longitude % 30
    whole = int(degree)
    minutes = int(round((degree - whole) * 60))
    if minutes == 60:
        whole += 1
        minutes = 0
    if whole == 30:
        whole = 0
        sign_index = (sign_index + 1) % 12
    return f"{whole:02d}°{minutes:02d}' {SIGNS[sign_index]}"


def calculate_transits():
    now_utc = datetime.now(timezone.utc)
    now_india = now_utc.astimezone(ZoneInfo("Asia/Kolkata"))
    decimal_hour = (
        now_utc.hour + now_utc.minute / 60
        + now_utc.second / 3600 + now_utc.microsecond / 3_600_000_000
    )
    jd_ut = swe.julday(
        now_utc.year, now_utc.month, now_utc.day, decimal_hour
    )

    flags = swe.FLG_MOSEPH | swe.FLG_SPEED
    rows = []

    for name, planet_id in PLANETS + [("Rahu", NODE_ID)]:
        tropical, _ = swe.calc_ut(jd_ut, planet_id, flags)
        sidereal, _ = swe.calc_ut(
            jd_ut, planet_id, flags | swe.FLG_SIDEREAL
        )
        trop_lon = tropical[0] % 360
        sid_lon = sidereal[0] % 360
        retro = tropical[3] < 0

        rows.append(
            f"{name} | Tropical: {sign_and_degree(trop_lon)} | "
            f"Sidereal Lahiri: {sign_and_degree(sid_lon)} | "
            f"{'Retrograde' if retro else 'Direct'}"
        )

        if name == "Rahu":
            rows.append(
                f"Ketu | Tropical: {sign_and_degree((trop_lon + 180) % 360)} | "
                f"Sidereal Lahiri: {sign_and_degree((sid_lon + 180) % 360)} | "
                f"{'Retrograde' if retro else 'Direct'}"
            )

    header = [
        "CALCULATED CURRENT TRANSITS",
        f"Timestamp: {now_india.strftime('%Y-%m-%d %H:%M:%S %Z')} "
        f"(India); {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "Geocentric ecliptic longitudes.",
        "Western column = tropical zodiac.",
        "Vedic column = sidereal zodiac, Lahiri ayanamsha.",
        f"Nodes = {NODE_MODE} node; Ketu is opposite Rahu.",
        "Swiss Ephemeris Moshier calculation mode.",
        "Do not assign houses from this block; no natal ascendant is supplied.",
        "",
    ]
    return "\n".join(header + rows)


TRANSIT_PATTERN = re.compile(
    r"\b(transit|transits|gochar|planetary position|planetary positions|"
    r"current planets|current planetary|today's planets|today planets|"
    r"right now|current sky|where is (?:jupiter|saturn|mars|venus|"
    r"mercury|rahu|ketu|the sun|the moon))\b|"
    r"गोचर|ग्रहों की स्थिति|वर्तमान ग्रह|आज के ग्रह",
    re.IGNORECASE
)


def asks_for_transits(text):
    return bool(TRANSIT_PATTERN.search(text or ""))


# -------------------- IMAGE PREPARATION --------------------

def prepare_image(image_bytes):
    with Image.open(io.BytesIO(image_bytes)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((2200, 2200))
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=92, optimize=True)
        return output.getvalue()


# -------------------- DISCORD --------------------

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Isolated memory for each user in each channel.
channel_histories = {}
active_requests = set()


@bot.event
async def on_ready():
    log.info("Logged in and online as %s", bot.user)


def error_status(exc):
    status = getattr(exc, "code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    try:
        return int(status)
    except (TypeError, ValueError):
        match = re.search(r"\b(429|500|502|503|504)\b", str(exc))
        return int(match.group(1)) if match else None


async def generate_with_retry(contents):
    # Two bounded retries for temporary server-side 5xx failures.
    delays = [2, 5]
    for attempt in range(3):
        try:
            return await asyncio.wait_for(
                async_client.models.generate_content(
                    model=MODEL_NAME,
                    contents=contents,
                    config=GENERATION_CONFIG,
                ),
                timeout=API_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            status = error_status(exc)
            if status in (500, 502, 503, 504) and attempt < 2:
                delay = delays[attempt]
                log.warning(
                    "Gemini HTTP %s; retrying in %s seconds "
                    "(attempt %s/3).",
                    status, delay, attempt + 1
                )
                await asyncio.sleep(delay)
                continue
            raise


async def send_long_message(message, text):
    chunks = []
    remaining = text.strip()
    while len(remaining) > MAX_DISCORD_CHARS:
        split_at = remaining.rfind("\n", 0, MAX_DISCORD_CHARS)
        if split_at < 500:
            split_at = remaining.rfind(" ", 0, MAX_DISCORD_CHARS)
        if split_at < 500:
            split_at = MAX_DISCORD_CHARS
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)

    for index, chunk in enumerate(chunks):
        if index == 0:
            await message.reply(chunk, mention_author=False)
        else:
            await message.channel.send(chunk)


@bot.event
async def on_message(message):
    if message.author.bot or bot.user is None:
        return
    if not bot.user.mentioned_in(message):
        return

    memory_key = (message.channel.id, message.author.id)
    if memory_key in active_requests:
        await message.reply(
            "I'm still finishing your previous reading. Please wait a moment.",
            mention_author=False
        )
        return

    active_requests.add(memory_key)

    try:
        clean_text = re.sub(
            rf"<@!?{bot.user.id}>", "", message.content
        ).strip()

        if not clean_text and not message.attachments:
            await message.reply(
                "Greetings traveller. I am MayaSutra. "
                "What would you like to explore today?",
                mention_author=False
            )
            return

        if not clean_text:
            clean_text = "Please examine the attached image carefully."

        now_local = datetime.now(ZoneInfo("Asia/Kolkata"))
        prompt_parts = [
            f"Current date and time: "
            f"{now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}.\n"
            f"User message: {clean_text}"
        ]

        history = channel_histories.get(memory_key, [])
        if history:
            prompt_parts.insert(
                0,
                "Recent conversation with this same user:\n"
                + "\n".join(history[-MAX_HISTORY_ITEMS:])
            )

        if asks_for_transits(clean_text):
            transit_data = await asyncio.to_thread(calculate_transits)
            prompt_parts.append(
                "Use this calculated ephemeris as authoritative. "
                "Do not substitute remembered positions:\n\n" + transit_data
            )

        for attachment in message.attachments:
            content_type = (attachment.content_type or "").lower()
            filename = attachment.filename.lower()
            is_image = (
                content_type.startswith("image/")
                or filename.endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".bmp")
                )
            )
            if not is_image:
                continue

            if attachment.size > MAX_IMAGE_BYTES:
                await message.reply(
                    "That image is larger than 8 MB. Please upload a smaller chart.",
                    mention_author=False
                )
                return

            raw_bytes = await attachment.read()
            try:
                jpeg_bytes = await asyncio.to_thread(
                    prepare_image, raw_bytes
                )
            except Exception:
                await message.reply(
                    "I couldn't read that image. Please upload a clear PNG or JPG.",
                    mention_author=False
                )
                return

            prompt_parts.append(
                types.Part.from_bytes(
                    data=jpeg_bytes,
                    mime_type="image/jpeg"
                )
            )
            prompt_parts[0] += (
                f"\nImage attached: {attachment.filename}. "
                "Read visible chart labels carefully; do not guess."
            )
            break

        async with message.channel.typing():
            started = asyncio.get_running_loop().time()
            response = await generate_with_retry(prompt_parts)
            elapsed = asyncio.get_running_loop().time() - started
            log.info(
                "Gemini response completed in %.2f seconds for user %s.",
                elapsed, message.author.id
            )

        answer = (response.text or "").strip()
        if not answer:
            answer = "I couldn't produce a readable answer this time. Please try again."

        history = channel_histories.setdefault(memory_key, [])
        history.extend([f"User: {clean_text}", f"MayaSutra: {answer}"])
        channel_histories[memory_key] = history[-MAX_HISTORY_ITEMS:]

        await send_long_message(message, answer)

    except asyncio.TimeoutError:
        log.warning("Gemini request timed out.")
        await message.reply(
            "The connection is taking too long. Please try again shortly.",
            mention_author=False
        )

    except Exception as exc:
        status = error_status(exc)
        log.exception("Message failed (HTTP status: %s).", status)

        if status == 429:
            reply = (
                "I've reached a temporary API rate limit. "
                "Please wait before trying again."
            )
        elif status in (500, 502, 503, 504):
            reply = (
                "Gemini is temporarily unavailable. Please try again shortly."
            )
        else:
            reply = (
                "I encountered a technical issue while preparing your response. "
                "Please try again."
            )

        await message.reply(reply, mention_author=False)

    finally:
        active_requests.discard(memory_key)


# -------------------- START --------------------

bot.run(DISCORD_TOKEN, reconnect=True)
    
