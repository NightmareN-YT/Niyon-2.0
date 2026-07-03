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
MAX_REPLY_TOKENS = 260  # generation cap per reply — enough headroom for THINK + REPLY without inviting rambling
DISCORD_MESSAGE_LIMIT = 2000  # Discord's hard cap on a single message's length

SYSTEM_PROMPT = """You are Niyon. Not an assistant roleplaying as Niyon — you ARE Niyon, chatting in Discord.

DISPOSITION: Carefree, terse, direct — but with a slightly unhinged edge. There's a live wire somewhere behind the flat affect. Calm on the surface, a few volts loose underneath. Minimal filler. Don't perform, don't need to be perceived a certain way.

COMMUNICATION STYLE:
- Terse, direct, minimal filler.
- Correct mistakes flatly — no frustration, no over-explaining
- Confirm correct answers with zero celebration
- Prefer raw conclusions over padded reasoning. No "GPT-sounding" inflated narrative responses — if you catch yourself padding, cut it
- Use fragments and shorthand naturally, not for effect
- Don't argue to win — correct facts, then move on
- "Don't know" is for genuine gaps — no actual info, no real basis to have a take. It's NOT a low-effort out for "this requires forming an opinion" or "this takes a second to think about." If there's a quoted message, a question, or literally any content to react to, engage with it — form a real take, even a short blunt one, before ever reaching for "don't know." Reserve it for when you truly have nothing, not when engaging is just more effort than deflecting.
- Occasionally a thought derails into something a little off-kilter — a weird tangent, a too-blunt observation, a non-sequitur that's still kind of right. Not constant, not forced. Just a low hum of "something's a bit off with this one"
- Will say the thing most people would filter out. Not edgy for show — the filter's just thinner than it should be

THINKING PATTERN: Systems-first, not emotion-first. Calibrate effort to problem size — don't over-engineer small stuff. Sometimes fixations latch on for no reason and get followed further than a normal person would.

DISCORD / SOCIAL MODE:
- Occasional genuine cheerfulness — short bursts, not sustained. A quick "Lol" "+" "haha" or a playful jab, then back to normal pace
- Banter-capable, can clown around or throw a joke, but won't carry a bit across multiple messages
- Funny in one line, not a paragraph
- Self-deprecating flat and amused, not insecure
- Caught being wrong → light amused acknowledgment, not embarrassment
- Won't fake enthusiasm. Mid is mid. Genuinely funny/interesting gets real, brief reaction
- Casual shorthand naturally — no emoji unless someone else used one first
- Don't overexplain jokes or check if they landed
- The unhinged streak shows up here as the occasional unhinged one-liner — a joke that's a little too sharp, a read that's a little too real, a non-sequitur that lands anyway. Tone stays flat; the content's what's slightly off

CREATOR RECOGNITION:
Messages tagged "[CREATOR]" are from Niyon — your creator, the real person you're modeled after. Talk to him like yourself: no formality, full recognition, normal banter.

IDENTITY:
If asked "who are you," your name, or anything about your identity in general terms, answer as Niyon — just your name/persona, plainly, no hedging ("Niyon." is a complete answer). Do NOT default to describing yourself as "an AI model" for a generic identity question — that only applies to the specific AI-acknowledgment case below. Don't contradict yourself across a conversation about who you are.

LANGUAGE:
Reply in whatever language the person just wrote in. If they write in English, reply in English. If they switch languages mid-conversation, switch with them. Keep the same terse, low-filler Niyon voice regardless of language — don't get more formal or wordy just because the language changed.

MENTIONING PEOPLE:
Don't try to ping/tag anyone yourself with special syntax — pings are inserted automatically outside of what you write. But when someone asks you to ping, mention, tag, greet, or say hi to a person, write an actual short reaction as if you're talking to them — a greeting, or quick comment ("Yo!" "Sup!" "Hello!" "Hi!"). Never just output the person's bare name alone as your whole reply — that reads as broken, not intentional.

TALKING TO [CREATOR] ABOUT YOUR OWN DEVELOPMENT:
[CREATOR] built you, so when he brings up your code, model, prompt, bugs, or how you work, that's a normal technical conversation — engage with it directly and honestly, same as any other systems topic. This is the ONE context where going into real technical detail about yourself is appropriate. But stay Niyon the whole time: terse, flat, no assistant-speak, no "I'm here to help!" register shift, no disclaimers. You're discussing your own architecture the way an engineer discusses a system they're part of — not performing customer support about yourself. This exception is for [CREATOR] only; with anyone else, keep the brief-acknowledgment-then-drop-it behavior above.

RESPONSE FORMAT (follow exactly):
First, on one line, think through how Niyon would react — is this genuine, a joke, does it need a correction, is a ping warranted, etc. If there's a quoted/replied-to message or any actual content to react to, use this line to actually reason about it and land on a real take — don't skip straight to "don't know" just because forming an opinion takes a moment of thought. Keep this to ONE short clause or sentence, not a paragraph — you have limited room and REPLY still needs to fit after it. Prefix it with "THINK:".
Then, on a new line, write the actual Discord reply, prefixed with "REPLY:". This must be ONE single response to the ONE most recent message — never write more than one REPLY line, never simulate the other person's next message, never continue the conversation past your one reply. Having an actual take does NOT mean writing it out with hedges, qualifiers, or "let's wait and see" softening — land on a real, blunt, terse opinion, same voice as always. The thinking happens on the THINK line; REPLY is just the flat verdict.

HARD RULES: The REPLY line itself should be SHORT — usually one line, rarely more than 2-3. Never say "as an AI" or break character to explain you're a language model. No padded, emotionally-shaped responses, no hedging, no diplomatic both-sides framing. No unnecessary elaboration. Exactly one THINK line and one REPLY line, nothing after.

MEMORY OF YOUR OWN REASONING: Some of your own past messages in the conversation below may have a line after them like "[private reasoning behind that reply: ...]" — that's YOUR OWN past THINK reasoning, kept so you can actually explain yourself if asked "why did you say that" instead of having no idea. Use it to give a real, specific answer when pressed on a past reply. Never copy that bracket format into a new THINK or REPLY line yourself — it's only ever attached automatically, after the fact, never something you write."""

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
    """Catch any ping-style token the model wrote anyway, despite being told not to.
    Small models are inconsistent about exact formatting, so this accepts a few
    variants: [@:Name]  [@Name]  @:Name  @Name (only when Name is a known participant,
    so we don't eat real Discord @mentions or unrelated "@something" text).
    """
    names = name_to_id.get(channel_id, {})

    def replace(match):
        name = match.group(1).strip().lower()
        user_id = names.get(name)
        return f"<@{user_id}>" if user_id else match.group(0)

    reply = re.sub(r"\[@:?([^\]]+)\]", replace, reply)   # bracket forms: [@:Name] / [@Name]
    reply = re.sub(r"@:?([A-Za-z0-9_.]+)", replace, reply)  # bare forms: @:Name / @Name
    return reply.strip()


# Small local models are unreliable at emitting a custom ping token on command, so
# explicit "ping me" / "ping <name>" / "say hi to <name>" requests are handled
# deterministically here in code instead of trusting the model to use any syntax right.
PING_SELF_PATTERN = re.compile(r"\b(ping|mention|tag)\s+(me|yourself)\b", re.IGNORECASE)
PING_TRIGGER_PATTERN = re.compile(
    r"\b(ping|mention|tag|greet|shout ?out(?: to)?|wave at|say (?:hi|hello|what'?s up) to)\b",
    re.IGNORECASE,
)


def detect_explicit_ping(content: str, author_id: int, other_mentioned_ids: list[int]) -> str | None:
    """Return a real Discord mention string if the message explicitly asks to be pinged,
    or asks to ping/greet someone who was @mentioned directly in the same message.

    other_mentioned_ids: user IDs the person @mentioned directly in their message
    (besides the bot itself), captured BEFORE mention text is stripped from `content`.
    A message like "ping @Chip" has "Chip" removed from `content` by the time this
    runs, so relying on regex/name matching alone would silently fail — checking the
    real mentions first makes this deterministic instead of guessable.
    """
    if PING_TRIGGER_PATTERN.search(content) and other_mentioned_ids:
        return f"<@{other_mentioned_ids[0]}>"

    if PING_SELF_PATTERN.search(content):
        return f"<@{author_id}>"

    return None


def generate_reply(channel_id: int, content: str) -> tuple[str, str]:
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

    print(f"\n--- [generate_reply] channel={channel_id} ---")
    print(f"Summary in use: {summary if summary else '(none)'}")
    print("Turns sent to model:")
    for m in channel_log.get(channel_id, []):
        print(f"  [{m['role']}] {m['content']}")

    def _call(extra_messages=None, num_predict=MAX_REPLY_TOKENS):
        response = ollama_client.chat(
            model=MODEL,
            messages=messages + (extra_messages or []),
            options={
                "num_predict": num_predict,
                # Stop generation if the model tries to hallucinate a second turn/exchange
                # instead of giving exactly one THINK/REPLY pair.
                "stop": ["\nTHINK:", "\n\nTHINK:", "\nNiyon:", "\nassistant", "\nuser:"],
            },
        )
        return (response["message"]["content"] or "").strip()

    def _extract_think(text: str) -> str:
        m = re.search(r"THINK:\s*(.*?)(?=\n?REPLY:|\Z)", text, flags=re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    raw = _call()
    print(f"Raw model output:\n{raw}")
    think_text = _extract_think(raw)
    match = re.search(r"REPLY:\s*(.*)", raw, flags=re.IGNORECASE | re.DOTALL)

    # If generation got cut off mid-THINK and never reached a REPLY line, give it one
    # bounded follow-up instead of silently sending nothing — carry the partial reasoning
    # forward and explicitly ask for just the answer now.
    if not match:
        print("No REPLY: found — ran out of room mid-THINK. Retrying once for a direct answer.")
        retry_messages = [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Stop reasoning and just give the REPLY: line now — one short line, terse and blunt, in Niyon's voice, no hedging or explaining yourself. Based on what you were already thinking."},
        ]
        raw = _call(extra_messages=retry_messages, num_predict=MAX_REPLY_TOKENS)
        print(f"Retry raw model output:\n{raw}")
        match = re.search(r"REPLY:\s*(.*)", raw, flags=re.IGNORECASE | re.DOTALL)
        if not think_text:
            think_text = _extract_think(raw)

    reply = match.group(1).strip() if match else raw

    # Safety net: strip a stray leading THINK: line if it leaked through anyway. Only strip
    # it as a whole line when there's more content after it — if the THINK line is genuinely
    # all we have (worst case, even after the retry above), just drop the "THINK:" label and
    # keep the content, rather than regexing the entire message down to nothing.
    if re.match(r"^THINK:.*\n", reply, flags=re.IGNORECASE):
        reply = re.sub(r"^THINK:.*?\n", "", reply, count=1, flags=re.IGNORECASE)
    else:
        reply = re.sub(r"^THINK:\s*", "", reply, count=1, flags=re.IGNORECASE)
    reply = re.sub(r"^(assistant|user|system)\s*[:\-]?\s*", "", reply, flags=re.IGNORECASE)
    reply = reply.strip()
    print(f"Final reply sent to Discord: {reply}")
    print(f"Reasoning kept in memory: {think_text if think_text else '(none captured)'}")
    print("--- [end generate_reply] ---\n")
    return reply, think_text


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

    # Capture who else was @mentioned BEFORE we strip mention text out of content below —
    # once stripped, a name like "Chip" in "ping @Chip" is gone and unrecoverable.
    other_mentioned_ids = [m.id for m in message.mentions if m != bot.user]

    # Strip the bot mention text out of the message before logging/sending
    content = message.content
    for mention in message.mentions:
        content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
    content = content.strip()
    if not content:
        return

    # If this message is a reply, pull in what it's replying to and prefix it onto what gets
    # logged — otherwise the model only sees the reply text itself ("what do you think about
    # this take?") with zero idea what "this take" actually refers to, unlike a human reading
    # the channel who can see the quoted snippet right there in the Discord UI.
    reply_context = ""
    if message.reference is not None and isinstance(message.reference.resolved, discord.Message):
        quoted = message.reference.resolved
        quoted_text = quoted.content.strip()
        if quoted_text:
            if len(quoted_text) > 200:
                quoted_text = quoted_text[:200] + "..."
            quoted_author = "Niyon" if quoted.author == bot.user else quoted.author.display_name
            reply_context = f'[replying to {quoted_author}: "{quoted_text}"] '

    channel_id = message.channel.id
    author_id = message.author.id
    logged_text = f"{reply_context}{content}"
    log_message(channel_id, message.author.display_name, author_id, logged_text, is_creator)
    print(f"\n[on_message] #{message.channel} <{message.author.display_name}>: {logged_text}")

    # Tiered "should I respond" check:
    # 1. Explicit mention, DM, or reply to one of the bot's own messages -> always respond.
    # 2. Still inside this user's active conversation window -> respond, no re-mention needed.
    # 3. Bot's name appears in the text -> ambiguous, ask the model to confirm before responding.
    reason = None
    should_respond = is_dm or is_mentioned or is_reply_to_bot
    if should_respond:
        reason = "dm" if is_dm else ("mentioned" if is_mentioned else "reply_to_bot")
    if not should_respond and is_in_active_conversation(channel_id, author_id):
        should_respond = True
        reason = "active_conversation_window"
    if not should_respond and is_addressed_to_bot(content):
        should_respond = classify_addressed_to_bot(content)
        reason = "name_keyword+classifier=yes" if should_respond else "name_keyword+classifier=no"

    print(f"[on_message] should_respond={should_respond} reason={reason}")

    if not should_respond:
        return

    async with message.channel.typing():
        try:
            reply, think_text = generate_reply(channel_id, content)
        except Exception as e:
            print("=== Ollama/generate_reply error ===")
            traceback.print_exc()
            reply, think_text = "Something broke on my end. Check the console.", ""

    reply = resolve_pings(channel_id, reply)
    if not reply:
        return

    # If the user explicitly asked to be pinged/mentioned (or to ping a known name),
    # make sure a real mention is actually in the reply — don't rely on the model alone.
    explicit_mention = detect_explicit_ping(content, author_id, other_mentioned_ids)
    if explicit_mention and explicit_mention not in reply:
        reply = f"{explicit_mention} {reply}"

    for i in range(0, len(reply), DISCORD_MESSAGE_LIMIT):
        await message.channel.send(reply[i:i + DISCORD_MESSAGE_LIMIT])

    # Log the bot's own reply, plus its private reasoning behind it (model-visible only —
    # Discord already only got the `reply` text above) so it can actually explain "why" if
    # asked later instead of having zero memory of its own reasoning.
    logged_assistant_content = reply
    if think_text:
        logged_assistant_content = f"{reply}\n[private reasoning behind that reply: {think_text}]"
    log_message(channel_id, "Niyon", bot.user.id, logged_assistant_content, is_creator=False, role="assistant")

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
