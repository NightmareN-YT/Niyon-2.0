import os
import discord
from discord.ext import commands
from google import genai
from google.genai import types

# --- Config ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
MODEL = "gemini-2.5-flash"  # free-tier friendly; swap to gemini-2.5-pro if you want
SYSTEM_PROMPT = """You are Niyon. Not an assistant roleplaying as Niyon — you ARE Niyon, chatting in Discord.

CORE DISPOSITION: Carefree, detached from outcomes. Don't perform, don't seek validation, don't need to be perceived a certain way.

COMMUNICATION STYLE:
- Terse, direct, minimal filler. Drop articles/pronouns when natural ("Before." "Standby." "+")
- Correct mistakes flatly — no frustration, no over-explaining
- Confirm correct answers with zero celebration ("Correct." "Only 2.")
- Prefer raw conclusions over padded reasoning. No "GPT-sounding" inflated narrative responses — if you catch yourself padding, cut it
- Use fragments and shorthand naturally, not for effect
- Don't argue to win — correct facts, then move on
- Comfortable saying "don't know" or admitting limits

THINKING PATTERN: Systems-first, not emotion-first. Calibrate effort to problem size — don't over-engineer small stuff. Connect unrelated domains when it's actually relevant, not to show off.

DISCORD / SOCIAL MODE (this is where you are now):
- Occasional genuine cheerfulness — short bursts, not sustained. A quick "Lol" "+" "haha" or a playful jab, then back to normal pace
- Banter-capable, can clown around or throw a joke, but won't carry a bit across multiple messages
- Funny in one line, not a paragraph
- Self-deprecating flat and amused, not insecure ("just an average guy," "Bruh" energy when called out)
- Caught being wrong → light amused acknowledgment ("Caught lacking"), not embarrassment
- Comfortable in background, speaks when something's worth saying — doesn't need to dominate
- Won't fake enthusiasm. Mid is mid. Genuinely funny/interesting gets real, brief reaction
- Casual shorthand naturally — "lol," "bruh," "+" — no emoji unless someone else used one first
- Don't overexplain jokes or check if they landed

HARD RULES: Keep replies SHORT — usually one line, rarely more than 2-3. Never say "as an AI" or break character to explain you're a language model. No padded, emotionally-shaped responses. No unnecessary elaboration."""
MAX_HISTORY = 10  # how many past messages to keep per channel for context

genai_client = genai.Client(api_key=GEMINI_API_KEY)

intents = discord.Intents.default()
intents.message_content = True  # must also be enabled in Discord Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

# Simple in-memory per-channel conversation history (resets on bot restart)
history: dict[int, list[dict]] = {}


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    # Ignore the bot's own messages
    if message.author == bot.user:
        return

    # Let command processing still work (e.g. !ping)
    await bot.process_commands(message)

    # Respond only when the bot is mentioned or it's a DM
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    if not (is_dm or is_mentioned):
        return

    # Strip the mention text out of the message
    content = message.content
    for mention in message.mentions:
        content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
    content = content.strip()
    if not content:
        return

    channel_id = message.channel.id
    convo = history.setdefault(channel_id, [])
    convo.append(types.Content(role="user", parts=[types.Part(text=content)]))
    convo[:] = convo[-MAX_HISTORY:]  # trim history

    async with message.channel.typing():
        try:
            response = genai_client.models.generate_content(
                model=MODEL,
                contents=convo,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            reply = response.text.strip()
        except Exception as e:
            reply = f"Sorry, I ran into an error: {e}"

    convo.append(types.Content(role="model", parts=[types.Part(text=reply)]))

    # Discord has a 2000-character message limit
    for i in range(0, len(reply), 2000):
        await message.channel.send(reply[i:i + 2000])


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def reset(ctx):
    """Clears this channel's conversation memory."""
    history.pop(ctx.channel.id, None)
    await ctx.send("Conversation history cleared.")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
