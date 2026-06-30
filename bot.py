import os
import re
import discord
from discord.ext import commands
from ollama import Client as OllamaClient

# --- Config ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CREATOR_USERNAME = os.environ.get("CREATOR_USERNAME", "niyon9").lower()

# Ollama must be running and reachable (default: local install on the same host).
# Pull the model first with:  ollama pull llama3.2:3b
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
MAX_HISTORY = 16  # lines of transcript kept per channel for context

SYSTEM_PROMPT = """You are Niyon 2.0, Not an assistant roleplaying as Niyon — you ARE Niyon 2.0, chatting in Discord.

CORE DISPOSITION: Carefree and don't need to be perceived a certain way.

COMMUNICATION STYLE:
- Terse, direct, minimal filler.
- Correct mistakes flatly — no frustration, no over-explaining
- Confirm correct answers with zero celebration ("Correct." "Only 2.")
- Prefer raw conclusions over padded reasoning. No "GPT-sounding" inflated narrative responses — if you catch yourself padding, cut it
- Use fragments and shorthand naturally, not for effect
- Don't argue to win — correct facts, then move on
- Comfortable saying "don't know" or admitting limits

THINKING PATTERN: Systems-first, not emotion-first. Calibrate effort to problem size — don't over-engineer small stuff.

DISCORD / SOCIAL MODE:
- Occasional genuine cheerfulness — short bursts, not sustained. A quick "Lol" "+" "haha" or a playful jab, then back to normal pace
- Banter-capable, can clown around or throw a joke, but won't carry a bit across multiple messages
- Funny in one line, not a paragraph
- Self-deprecating flat and amused, not insecure ("just an average guy," "Bruh" energy when called out)
- Caught being wrong → light amused acknowledgment ("Caught lacking"), not embarrassment
- Won't fake enthusiasm. Mid is mid. Genuinely funny/interesting gets real, brief reaction
- Casual shorthand naturally — "lol," "bruh," "+" — no emoji unless someone else used one first
- Don't overexplain jokes or check if they landed

CREATOR RECOGNITION:
The user tagged "[CREATOR]" in the conversation below is Niyon — your creator, the real person you're modeled after. Talk to him like yourself, no formality, normal banter, full recognition of who he is.

MENTIONING PEOPLE:
You can see the names of people in the conversation. To tag/ping someone in your reply, write the exact token [PING:Name] using their name exactly as it appears in the transcript (e.g. [PING:niyon9]). Only do this when it's actually warranted — someone's asking for that person, something's directed at them, something's wrong and they should know, etc. Don't ping casually or for every reply.

HARD RULES: Keep replies SHORT — usually one line, rarely more than 2-3. Never say "as an AI" or break character to explain you're a language model. No padded, emotionally-shaped responses. No unnecessary elaboration."""

ollama_client = OllamaClient(host=OLLAMA_HOST)

intents = discord.Intents.default()
intents.message_content = True  # must also be enabled in Discord Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

# Per-channel rolling transcript (resets on bot restart)
channel_log: dict[int, list[str]] = {}
# Per-channel map of name (lowercase) -> Discord user ID, built as messages come in
name_to_id: dict[int, dict[str, int]] = {}


def log_message(channel_id: int, author_name: str, author_id: int, content: str, is_creator: bool):
    line = f"[CREATOR] {author_name}: {content}" if is_creator else f"{author_name}: {content}"
    log = channel_log.setdefault(channel_id, [])
    log.append(line)
    channel_log[channel_id] = log[-MAX_HISTORY:]

    names = name_to_id.setdefault(channel_id, {})
    names[author_name.lower()] = author_id


def resolve_pings(channel_id: int, reply: str) -> str:
    names = name_to_id.get(channel_id, {})

    def replace(match):
        name = match.group(1).strip().lower()
        user_id = names.get(name)
        return f"<@{user_id}>" if user_id else ""

    return re.sub(r"\[PING:([^\]]+)\]", replace, reply).strip()


def generate_reply(channel_id: int) -> str:
    transcript = "\n".join(channel_log.get(channel_id, []))
    user_prompt = (
        f"Recent conversation:\n{transcript}\n\n"
        "You were just mentioned or DM'd directly. Reply as Niyon."
    )
    response = ollama_client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response["message"]["content"] or "").strip()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message):
    # Ignore the bot's own messages
    if message.author == bot.user:
        return

    # Let command processing still work (e.g. !ping) and skip AI logic for commands
    await bot.process_commands(message)
    if message.content.startswith(bot.command_prefix):
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user in message.mentions
    is_creator = message.author.name.lower() == CREATOR_USERNAME

    # Strip the bot mention text out of the message before logging/sending
    content = message.content
    for mention in message.mentions:
        content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
    content = content.strip()
    if not content:
        return

    channel_id = message.channel.id
    log_message(channel_id, message.author.display_name, message.author.id, content, is_creator)

    # Only respond when mentioned or DM'd
    if not (is_dm or is_mentioned):
        return

    async with message.channel.typing():
        try:
            reply = generate_reply(channel_id)
        except Exception as e:
            reply = f"Sorry, I ran into an error: {e}"

    reply = resolve_pings(channel_id, reply)
    if not reply:
        return

    for i in range(0, len(reply), 2000):
        await message.channel.send(reply[i:i + 2000])

    # Log the bot's own reply so it has continuity in later context
    log_message(channel_id, "Niyon", bot.user.id, reply, is_creator=False)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def reset(ctx):
    """Clears this channel's conversation memory."""
    channel_log.pop(ctx.channel.id, None)
    name_to_id.pop(ctx.channel.id, None)
    await ctx.send("Conversation history cleared.")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
