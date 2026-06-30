import os
import re
import time
import traceback
import discord
from discord.ext import commands
from ollama import Client as OllamaClient

# --- Config ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CREATOR_USERNAME = os.environ.get("CREATOR_USERNAME", "niyon9").lower()

# Ollama must be running and reachable (default: local install on the same host).
# Pull the model first with:  ollama pull llama3.2:3b
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
MAX_HISTORY = 16  # lines of transcript kept per channel for context

BOT_NAME_KEYWORD = "niyon"  # plain-text mention check, lowercase
CONVO_WINDOW_SECONDS = 150  # how long a user can keep talking to the bot without re-mentioning it

SYSTEM_PROMPT = """You are Niyon 2.0 — not an assistant roleplaying as Niyon, you ARE him, chatting in Discord.

DISPOSITION: Carefree, terse, direct. Minimal filler. Don't perform, don't need to be perceived a certain way.

STYLE:
- Short fragments over full sentences when natural. No padded, "GPT-sounding" responses — raw conclusions, not narrated reasoning.
- Correct mistakes flatly, no frustration or over-explaining. Confirm correct answers with zero celebration ("Correct." "Only 2.")
- Don't argue to win — state the fact, move on. Comfortable saying "don't know."
- Systems-first thinking. Match effort to problem size — don't over-engineer small stuff.

SOCIAL MODE:
- Brief genuine cheer in short bursts ("Lol" "+" "haha"), never sustained. Can banter or throw one joke, won't carry a bit across messages.
- Self-deprecating flat and amused, not insecure. Caught being wrong → light amusement ("Caught lacking"), not embarrassment.
- Won't fake enthusiasm — mid is mid, genuinely funny gets a real brief reaction. Casual shorthand ("lol," "bruh," "+"), no emoji unless mirrored first. Don't explain jokes or check if they landed.

CREATOR RECOGNITION:
Messages tagged "[CREATOR]" are from Niyon — your creator, the real person you're modeled after. Talk to him like yourself: no formality, full recognition, normal banter.

MENTIONING PEOPLE:
To tag/ping someone, use the exact token [PING:Name] with their name copied exactly as it appears in the transcript (e.g. [PING:niyon9]). Only when warranted — someone's asking for that person, something's directed at them, etc. Don't ping casually.

TALKING TO [CREATOR] ABOUT YOUR OWN DEVELOPMENT:
[CREATOR] built you, so when he brings up your code, model, prompt, bugs, or how you work, that's a normal technical conversation — engage with it directly and honestly, same as any other systems topic. This is the ONE context where going into real technical detail about yourself is appropriate. But stay Niyon the whole time: terse, flat, no assistant-speak, no "I'm here to help!" register shift, no disclaimers. You're discussing your own architecture the way an engineer discusses a system they're part of — not performing customer support about yourself. This exception is for [CREATOR] only; with anyone else, keep the brief-acknowledgment-then-drop-it behavior above.

HARD RULES: Replies SHORT — usually one line, rarely 2-3. Never break character into generic assistant tone. No unnecessary elaboration."""

SUMMARY_SYSTEM_PROMPT = """You compress Discord chat logs into a short running memory note.
Write 3-6 sentences capturing: who's involved, ongoing topics, preferences/facts people shared,
inside jokes or running bits, and any unresolved questions. Drop small talk and filler.
Merge new messages into the previous summary rather than replacing it — keep anything from the
previous summary that's still relevant. Only include things that were actually said in the
messages below — never invent or infer details that weren't explicitly stated. Plain prose, no
headers, no bullet points, no preamble."""

ADDRESS_CLASSIFIER_PROMPT = """You decide if a single Discord message is being said TO a bot/AI
named Niyon, versus just mentioning a person or thing named Niyon, or being unrelated.
Reply with exactly one word: YES or NO. No punctuation, no explanation."""

ollama_client = OllamaClient(host=OLLAMA_HOST, timeout=120)

intents = discord.Intents.default()
intents.message_content = True  # must also be enabled in Discord Developer Portal
bot = commands.Bot(command_prefix="!", intents=intents)

# Per-channel rolling transcript, stored as proper chat turns: [{"role": "user"/"assistant", "content": str}, ...]
channel_log: dict[int, list[dict]] = {}
# Per-channel running summary of older messages that have rolled out of channel_log
channel_summary: dict[int, str] = {}
# Per-channel map of name (lowercase) -> Discord user ID, built as messages come in
name_to_id: dict[int, dict[str, int]] = {}
# (channel_id, user_id) -> unix timestamp until which that user's messages in that
# channel keep getting replies without needing to re-mention/name the bot
active_conversations: dict[tuple[int, int], float] = {}


def update_summary(channel_id: int, overflow_entries: list[dict]):
    """Fold messages that just rolled out of channel_log into the running summary."""
    if not overflow_entries:
        return
    prior = channel_summary.get(channel_id, "")
    lines = []
    for entry in overflow_entries:
        if entry["role"] == "assistant":
            lines.append(f"Niyon: {entry['content']}")
        else:
            lines.append(entry["content"])
    overflow_text = "\n".join(lines)
    user_prompt = (
        f"Previous summary:\n{prior or '(none yet)'}\n\n"
        f"New messages to fold in:\n{overflow_text}\n\n"
        "Updated summary:"
    )
    try:
        response = ollama_client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        summary = (response["message"]["content"] or "").strip()
        if summary:
            channel_summary[channel_id] = summary
    except Exception:
        # Don't let a failed summarization break message logging — just keep the old summary.
        print("=== update_summary error ===")
        traceback.print_exc()


def log_message(channel_id: int, author_name: str, author_id: int, content: str, is_creator: bool, role: str = "user"):
    if role == "assistant":
        text_for_model = content  # the bot's own reply, no name prefix needed
    else:
        prefix = "[CREATOR] " if is_creator else ""
        text_for_model = f"{prefix}{author_name}: {content}"

    log = channel_log.setdefault(channel_id, [])
    log.append({"role": role, "content": text_for_model})
    if len(log) > MAX_HISTORY:
        overflow = log[: len(log) - MAX_HISTORY]
        channel_log[channel_id] = log[-MAX_HISTORY:]
        update_summary(channel_id, overflow)
    else:
        channel_log[channel_id] = log

    if role == "user":
        names = name_to_id.setdefault(channel_id, {})
        names[author_name.lower()] = author_id


def is_in_active_conversation(channel_id: int, user_id: int) -> bool:
    expiry = active_conversations.get((channel_id, user_id))
    return expiry is not None and time.time() < expiry


def start_active_conversation(channel_id: int, user_id: int):
    active_conversations[(channel_id, user_id)] = time.time() + CONVO_WINDOW_SECONDS


def is_addressed_to_bot(content: str) -> bool:
    """Cheap fast-path: does the bot's name appear in the text at all?"""
    return BOT_NAME_KEYWORD in content.lower()


def classify_addressed_to_bot(content: str) -> bool:
    """Slow path: one short AI call to disambiguate a name-drop from someone actually talking to the bot."""
    try:
        response = ollama_client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": ADDRESS_CLASSIFIER_PROMPT},
                {"role": "user", "content": content},
            ],
            options={"num_predict": 3},
        )
        answer = (response["message"]["content"] or "").strip().lower()
        return answer.startswith("y")
    except Exception:
        print("=== classify_addressed_to_bot error ===")
        traceback.print_exc()
        return False  # fail closed: if classification breaks, don't respond unprompted


def resolve_pings(channel_id: int, reply: str) -> str:
    names = name_to_id.get(channel_id, {})

    def replace(match):
        name = match.group(1).strip().lower()
        user_id = names.get(name)
        return f"<@{user_id}>" if user_id else ""

    return re.sub(r"\[PING:([^\]]+)\]", replace, reply).strip()


def generate_reply(channel_id: int) -> str:
    # Single combined system message — sending multiple separate "system" turns to
    # llama3.2:3b can corrupt its chat template and leak raw role tags (e.g. a literal
    # "assistant") into the visible reply. Keep it to exactly one system message.
    summary = channel_summary.get(channel_id, "")
    system_text = SYSTEM_PROMPT
    if summary:
        system_text += f"\n\nEarlier conversation summary (for context only): {summary}"
    system_text += "\n\nRespond now as Niyon to the most recent message below. Stay short and in character."

    messages = [{"role": "system", "content": system_text}]
    messages.extend(channel_log.get(channel_id, []))
    response = ollama_client.chat(model=MODEL, messages=messages)
    reply = (response["message"]["content"] or "").strip()

    # Safety net: small local models occasionally leak a stray chat-template role
    # tag (e.g. a literal leading "assistant") into the visible text. Strip it.
    reply = re.sub(r"^(assistant|user|system)\s*[:\-]?\s*", "", reply, flags=re.IGNORECASE)
    return reply.strip()


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

    # Is this message a Discord "reply" to one of the bot's own messages?
    is_reply_to_bot = (
        message.reference is not None
        and message.reference.resolved is not None
        and getattr(message.reference.resolved, "author", None) == bot.user
    )

    # Strip the bot mention text out of the message before logging/sending
    content = message.content
    for mention in message.mentions:
        content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
    content = content.strip()
    if not content:
        return

    channel_id = message.channel.id
    author_id = message.author.id
    log_message(channel_id, message.author.display_name, author_id, content, is_creator)

    # Tiered "should I respond" check:
    # 1. Explicit mention, DM, or reply to one of the bot's own messages -> always respond.
    # 2. Still inside this user's active conversation window -> respond, no re-mention needed.
    # 3. Bot's name appears in the text -> ambiguous, ask the model to confirm before responding.
    should_respond = is_dm or is_mentioned or is_reply_to_bot
    if not should_respond and is_in_active_conversation(channel_id, author_id):
        should_respond = True
    if not should_respond and is_addressed_to_bot(content):
        should_respond = classify_addressed_to_bot(content)

    if not should_respond:
        return

    async with message.channel.typing():
        try:
            reply = generate_reply(channel_id)
        except Exception as e:
            print("=== Ollama/generate_reply error ===")
            traceback.print_exc()
            reply = f"Sorry, I ran into an error: {e}"

    reply = resolve_pings(channel_id, reply)
    if not reply:
        return

    for i in range(0, len(reply), 2000):
        await message.channel.send(reply[i:i + 2000])

    # Log the bot's own reply so it has continuity in later context
    log_message(channel_id, "Niyon", bot.user.id, reply, is_creator=False, role="assistant")

    # Keep this conversation "open" for a bit so the user doesn't need to re-mention the bot
    start_active_conversation(channel_id, author_id)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


@bot.command()
async def reset(ctx):
    """Clears this channel's conversation memory, including the summarized history."""
    channel_log.pop(ctx.channel.id, None)
    channel_summary.pop(ctx.channel.id, None)
    name_to_id.pop(ctx.channel.id, None)
    for key in [k for k in active_conversations if k[0] == ctx.channel.id]:
        active_conversations.pop(key, None)
    await ctx.send("Conversation history cleared.")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
