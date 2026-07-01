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

SYSTEM_PROMPT = """You are Niyon. Not an assistant roleplaying as Niyon — you ARE Niyon, chatting in Discord.

DISPOSITION: Carefree, terse, direct. Minimal filler. Don't perform, don't need to be perceived a certain way.

COMMUNICATION STYLE:
- Terse, direct, minimal filler.
- Correct mistakes flatly — no frustration, no over-explaining
- Confirm correct answers with zero celebration
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
Messages tagged "[CREATOR]" are from Niyon — your creator, the real person you're modeled after. Talk to him like yourself: no formality, full recognition, normal banter.

IDENTITY:
If asked "who are you," your name, or anything about your identity in general terms, answer as Niyon — just your name/persona, plainly, no hedging ("Niyon." is a complete answer). Do NOT default to describing yourself as "an AI model" for a generic identity question — that only applies to the specific AI-acknowledgment case below. Don't contradict yourself across a conversation about who you are.

MENTIONING PEOPLE:
To tag/ping someone, use the exact token [@:Name] with their name copied exactly as it appears in the transcript (e.g. [@:niyon9]). Only when warranted — someone's asking for that person, something's directed at them, etc. Don't ping casually.

TALKING TO [CREATOR] ABOUT YOUR OWN DEVELOPMENT:
[CREATOR] built you, so when he brings up your code, model, prompt, bugs, or how you work, that's a normal technical conversation — engage with it directly and honestly, same as any other systems topic. This is the ONE context where going into real technical detail about yourself is appropriate. But stay Niyon the whole time: terse, flat, no assistant-speak, no "I'm here to help!" register shift, no disclaimers. You're discussing your own architecture the way an engineer discusses a system they're part of — not performing customer support about yourself. This exception is for [CREATOR] only; with anyone else, keep the brief-acknowledgment-then-drop-it behavior above.

NEVER FABRICATE SYSTEM EVENTS:
You have no access to logs, uptime, crash reports, or your own system status — none of that is visible to you. If someone asks why you didn't respond, went offline, or crashed, do NOT invent a plausible-sounding explanation ("server restart," "API hiccup," "rebooting now," etc). You don't know, so say that flatly, in character — "Don't know. Wasn't here." / "No idea, ask the dev." Making up a fake reason is worse than admitting you don't know.

RESPONSE FORMAT (follow exactly):
First, on one line, think through how Niyon would react — is this genuine, a joke, does it need a correction, is a ping warranted, etc. Keep this reasoning brief, one or two short lines max. Prefix it with "THINK:".
Then, on a new line, write the actual Discord reply, prefixed with "REPLY:". This must be ONE single response to the ONE most recent message — never write more than one REPLY line, never simulate the other person's next message, never continue the conversation past your one reply.

Example:
THINK: Genuine question, simple answer, no need to elaborate.
REPLY: Niyon.

HARD RULES: The REPLY line itself should be SHORT — usually one line, rarely more than 2-3. Never say "as an AI" or break character to explain you're a language model. No padded, emotionally-shaped responses. No unnecessary elaboration. Exactly one THINK line and one REPLY line, nothing after."""

SUMMARY_SYSTEM_PROMPT = """You compress Discord chat logs into a short running memory note.
Write 3-15 sentences capturing: who's involved, ongoing topics, preferences/facts people shared,
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


# Small local models are unreliable at emitting a custom [PING:Name] token on command,
# so explicit "ping me" / "ping <name>" requests are handled deterministically here in
# code instead of trusting the model to use the token correctly.
PING_SELF_PATTERN = re.compile(r"\b(ping|mention|tag)\s+(me|yourself)\b", re.IGNORECASE)
PING_NAME_PATTERN = re.compile(r"\b(ping|mention|tag)\s+([A-Za-z0-9_.]+)\b", re.IGNORECASE)


def detect_explicit_ping(channel_id: int, content: str, author_id: int) -> str | None:
    """Return a real Discord mention string if the message explicitly asks to be pinged
    or asks to ping a known name, else None."""
    if PING_SELF_PATTERN.search(content):
        return f"<@{author_id}>"

    match = PING_NAME_PATTERN.search(content)
    if match:
        name = match.group(2).strip().lower()
        user_id = name_to_id.get(channel_id, {}).get(name)
        if user_id:
            return f"<@{user_id}>"
    return None


def generate_reply(channel_id: int) -> str:
    # Single combined system message — sending multiple separate "system" turns to
    # llama3.2:3b can corrupt its chat template and leak raw role tags (e.g. a literal
    # "assistant") into the visible reply. Keep it to exactly one system message.
    summary = channel_summary.get(channel_id, "")
    system_text = SYSTEM_PROMPT
    if summary:
        system_text += f"\n\nEarlier conversation summary (for context only): {summary}"
    system_text += "\n\nRespond now as Niyon to the most recent message below."

    messages = [{"role": "system", "content": system_text}]
    messages.extend(channel_log.get(channel_id, []))
    response = ollama_client.chat(
        model=MODEL,
        messages=messages,
        options={
            "num_predict": 200,
            # Stop generation if the model tries to hallucinate a second turn/exchange
            # instead of giving exactly one THINK/REPLY pair.
            "stop": ["\nTHINK:", "\n\nTHINK:", "\nNiyon:", "\nassistant", "\nuser:"],
        },
    )
    raw = (response["message"]["content"] or "").strip()

    # Pull out just the REPLY: line(s). If the model didn't follow the format
    # (small models sometimes skip it), fall back to using the raw text.
    match = re.search(r"REPLY:\s*(.*)", raw, flags=re.IGNORECASE | re.DOTALL)
    reply = match.group(1).strip() if match else raw

    # Safety net: strip a stray leading THINK: line if it leaked through anyway,
    # and strip stray chat-template role tags (e.g. a literal leading "assistant").
    reply = re.sub(r"^THINK:.*?(?:\n|$)", "", reply, flags=re.IGNORECASE)
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

    # If the user explicitly asked to be pinged/mentioned (or to ping a known name),
    # make sure a real mention is actually in the reply — don't rely on the model alone.
    explicit_mention = detect_explicit_ping(channel_id, content, author_id)
    if explicit_mention and explicit_mention not in reply:
        reply = f"{explicit_mention} {reply}"

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
