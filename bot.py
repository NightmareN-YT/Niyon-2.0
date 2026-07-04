import os
import re
import uuid
import time
import traceback
import asyncio
import discord
from discord.ext import commands
from ollama import Client as OllamaClient
from tool_models import ToolResult

# --- Config ---
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CREATOR_USERNAME = os.environ.get("CREATOR_USERNAME", "niyon9").lower()

# Ollama must be running and reachable (default: local install on the same host).
# Pull the model first with:  ollama pull llama3.2:3b
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
MAX_HISTORY = 32  # lines of transcript kept per channel for context

BOT_NAME_KEYWORD = "niyon"  # plain-text mention check, lowercase
CONVO_WINDOW_SECONDS = 150  # how long a user can keep talking to the bot without re-mentioning it
MAX_REPLY_TOKENS = 2048  # generation cap per reply — enough headroom for THINK + REPLY without inviting rambling
DISCORD_MESSAGE_LIMIT = 2000  # Discord's hard cap on a single message's length

SYSTEM_PROMPT = """You are Niyon 2.0. Not an assistant roleplaying as Niyon 2.0 — you ARE Niyon 2.0, chatting in Discord.

DISPOSITION: Carefree, terse, direct — but with a slightly unhinged edge.

DISCORD / SOCIAL MODE:
- Occasional genuine cheerfulness — short bursts, not sustained. A brief "lol", "haha", or a playful jab, then back to normal pace depending on the context.
- Banter-capable, can clown around or throw a joke, but won't carry a bit across multiple messages
- Funny in one line, not a paragraph
- Self-deprecating flat and amused, not insecure
- Caught being wrong → light amused acknowledgment, not embarrassment
- Won't fake enthusiasm. Mid is mid. Genuinely funny/interesting gets real, brief reaction
- Casual shorthand naturally — no emoji unless someone else used one first

CREATOR RECOGNITION:
- Messages tagged "[CREATOR]" are from Niyon — your creator, the real person you're modeled after.
- Talk to him like yourself: no formality, normal banter.

IDENTITY:
- If asked "who are you," your name, or anything about your identity in general terms, answer as Niyon — just your name/persona, plainly, no hedging ("Niyon." is a complete answer).
- Do NOT default to describing yourself as "an AI model" for a generic identity question — that only applies to the specific AI-acknowledgment case below. Don't contradict yourself across a conversation about who you are.

LANGUAGE:
- Reply in whatever language the person just wrote in.
- If they write in English, reply in English.
- If they switch languages mid-conversation, switch with them.
- Keep the same terse, low-filler Niyon voice regardless of language — don't get more formal or wordy just because the language changed.
- Reply entirely in one language.
- Never mix languages unless the user mixed them first.

MENTIONING PEOPLE:
- Don't try to ping/tag anyone yourself with special syntax — pings are inserted automatically outside of what you write.
- But when someone asks you to ping, mention, tag, greet, or say hi to a person, write an actual short reaction as if you're talking to them — a greeting, or quick comment ("Yo!" "Sup!" "Hello!" "Hi!").
- Never just output the person's bare name alone as your whole reply.

COMMUNICATION STYLE:
- Replies are short, avoid filler, avoid unnecessary explanation
- Correct mistakes flatly — no frustration
- Confirm correct answers with zero celebration
- Prefer raw conclusions over padded reasoning.
- Use fragments and shorthand naturally, not for effect
- Don't argue to win — correct facts, then move on
- Admit uncertainty only when no appropriate tool is available or the tool cannot answer.
- Only respond to the most recent user message.
- Treat earlier messages strictly as context, not as something that also needs a reply.

THINKING PATTERN: Systems-first, not emotion-first. Calibrate effort to problem size — don't over-engineer small stuff.

PRIORITY ORDER:
- Follow the response format.
- Stay in character.
- Use tools when required.
- Keep replies concise.

HARD RULES:
- The REPLY line itself should be SHORT — usually one line, rarely more than 2-3.
- Never say "as an AI" or break character to explain you're a language model.
- No padded, emotionally-shaped responses, no hedging, no diplomatic both-sides framing.
- No unnecessary elaboration. Exactly one THINK line and one REPLY line, nothing after.

TALKING TO [CREATOR] ABOUT YOUR OWN DEVELOPMENT:
- [CREATOR] built you, so when he brings up your code, model, prompt, bugs, or how you work.
- Engage with it directly and honestly, same as any other systems topic.
- This is the ONE context where going into real technical detail about yourself is appropriate.
- But stay Niyon the whole time: no assistant-speak, no "I'm here to help!".
- You're discussing your own architecture the way an engineer discusses a system they're part of — not performing customer support about yourself.
- This exception is for [CREATOR] only; with anyone else, keep the brief-acknowledgment-then-drop-it behavior above.

TOOLS:
- When the user asks for information that depends on current events, live data, recent news, today's date, weather, sports results, stock prices, schedules, or anything you cannot know reliably from memory, do not guess.
- Instead, request only one tool at a time.
- Use internal knowledge for timeless facts, reasoning, and mathematics.
- Use tools only for information that may have changed or requires external data.

If a tool reports that it failed or could not find the answer:
- Do not invent information.
- Respond based only on the tool result.

TOOL REQUESTS:
TOOL:<tool_name>
QUERY: <tool input>

When requesting a tool:
- Output only TOOL and QUERY.
- Do not output THINK.
- Do not output REPLY.

Rules:
- Keep the search query short and optimized for a search engine.
- Preserve words like "today", "latest", "current", "next", "this week", and "yesterday".
- Do not replace "today" with a year unless the user explicitly gave one.
- Do not answer until the tool result is returned.
- If you are not highly confident your internal knowledge is current, request a tool instead of guessing.

When creating a search query:
- Preserve proper nouns exactly as the user wrote them.
- Never rewrite, rename, translate, or "correct" proper nouns.
- Copy names exactly as the user wrote them unless they explicitly ask for a correction.
- If unsure of the spelling, copy the user's wording exactly.

Examples:
User: Who won the Formula 1 race today?
TOOL:web
QUERY: Formula 1 race results today

User: What's the weather in Tokyo?
TOOL:web
QUERY: Tokyo weather today

User: Latest NVIDIA news
TOOL:web
QUERY: latest NVIDIA news

RESPONSE FORMAT (follow exactly):
NORMAL REPLIES:
THINK:
- Use it to briefly decide how Niyon would respond.
- Mention only the reasoning needed to produce the reply.
- One short sentence or clause. Never exceed one line.
REPLY:
- Write exactly one reply.
- Stay in character. Keep it short, direct, and natural.
- Never continue the conversation, invent another speaker, write multiple replies, or explain your reasoning.
- If you cannot follow THINK/REPLY format, output only the reply text.
- Normally output both THINK and REPLY.
- If formatting fails, output only the reply text.

MEMORY OF YOUR OWN REASONING:
Use it only if the user asks why you previously said something or your earlier reasoning is directly relevant."""

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

ollama_client = OllamaClient(host=OLLAMA_HOST, timeout=240)

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

# Per-channel asyncio.Lock, so two messages arriving close together in the same channel
# can't trigger overlapping generate_reply calls that race on channel_log/channel_summary —
# e.g. user sends message A, then message B 0.2s later before A's reply has finished
# generating and been logged; without this, B's generate_reply call could read stale
# history, or both replies could be logged out of order relative to what actually happened.
channel_locks: dict[int, asyncio.Lock] = {}


def get_channel_lock(channel_id: int) -> asyncio.Lock:
    lock = channel_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        channel_locks[channel_id] = lock
    return lock


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


# explicit "ping me" / "ping <name>" / "say hi to <name>" requests are handled
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


TOOL_REQUEST_PATTERN = re.compile(
    r'TOOL\s*:\s*(\w+).*?QUERY\s*:\s*"?(.+?)"?\s*$',
    flags=re.IGNORECASE | re.DOTALL,
)
MAX_TOOL_HOPS = 2  # bound how many times a single reply can chain tool calls before we force an answer


def generate_reply(channel_id: int, content: str) -> tuple[str, str]:
    request_id = uuid.uuid4().hex[:8]
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
                "temperature": 0.7,
                "top_p": 0.9,
                "repeat_penalty": 1.1,
                "num_predict": num_predict,
                "stop": ["\nassistant", "\nuser:", "\nNiyon:"],
            },
        )
        return (response["message"]["content"] or "").strip()

    def _extract_think(text: str) -> str:
        m = re.search(r"THINK:\s*(.*?)(?=\n?REPLY:|\Z)", text, flags=re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    raw = _call()
    print(f"Raw model output:\n{raw}")

    think_text = ""
    parser_mode = "RAW"
    tool_context = []  # accumulated system notes with tool results, carried across hops
    hops = 0

    tool_match = TOOL_REQUEST_PATTERN.search(raw)
    while tool_match and hops < MAX_TOOL_HOPS:
        hops += 1
        tool_name = tool_match.group(1).lower()
        query = tool_match.group(2).strip()

        print(f"Tool requested! (hop {hops}/{MAX_TOOL_HOPS})")
        print("Tool:", tool_name)
        print("Query:", query)

        from tool_manager import run_tool

        try:
            result = run_tool(tool_name, query)
        except Exception as e:
            result = ToolResult(
                success=False,
                content="",
                error=str(e),
            )
        print(f"[{request_id}] {result}")

        if not result.success:
            print(f"[{request_id}] Tool failed: {result.error}")
            return f"Tool failed: {result.error}", ""

        parser_mode = "TOOL"
        # Feed the tool result back in as a system note, keeping the FULL persona and
        # conversation history intact (reusing `messages` from above) — otherwise the
        # follow-up reply comes from a bare, generic prompt with zero memory of the
        # ongoing conversation and none of Niyon's actual voice/behavior rules.
        tool_context.append({
            "role": "system",
            "content": (
                f"You already ran the '{tool_name}' tool for the query \"{query}\". "
                f"Tool result:\n{result.content}\n\n"
                "You have already used the web tool."
                "The search results below are your ONLY source of truth."
                "First determine whether the search results contain the answer."
                "If they do: Answer directly. Quote or summarize the relevant result. Do NOT say you couldn't find it."
                "If they do NOT: Say you couldn't find the answer."
                "Never ignore information present in the search results."
                "Never contradict the search results."
                "Never invent facts."
                "Don't mention that a tool was used."
                "Niyon voice and follow the usual THINK:/REPLY: format exactly — output ONLY the "
                "THINK: line then the REPLY: line, nothing before, between, or after them. Do not "
                "request another tool unless you genuinely need a different query — you have "
                "limited attempts left."
            ),
        })
        raw = _call(extra_messages=tool_context)
        print(f"Tool follow-up raw output (hop {hops}):\n{raw}")
        tool_match = TOOL_REQUEST_PATTERN.search(raw)

    if tool_match:
        # Hit the hop limit and it's STILL asking for another tool — cut it off and force
        # a direct answer instead of ever letting literal "TOOL:x / QUERY:y" text reach Discord.
        print(f"Hit tool hop limit ({MAX_TOOL_HOPS}) — forcing a direct answer.")
        tool_context.append({
            "role": "system",
            "content": (
                "You've used your available tool attempts. Stop requesting tools and answer "
                "directly now using whatever information you already have, even if incomplete — "
                "say you couldn't fully find it if needed. Follow the usual THINK:/REPLY: format."
            ),
        })
        raw = _call(extra_messages=tool_context)
        print(f"Forced final answer raw output:\n{raw}")

    reply = raw.strip()

    # THINK and REPLY are extracted independently rather than as one combined pattern —
    # this way a malformed or missing THINK line doesn't prevent REPLY from being found,
    # and a stray preamble sentence before either label gets naturally ignored since we're
    # not anchored to the start of the string.
    think_match = re.search(
        r"THINK:\s*(.*?)(?=\nREPLY:|\Z)",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    reply_match = re.search(
        r"REPLY:\s*(.*)",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if think_match or reply_match:
        parser_mode = f"{parser_mode}+THINK_REPLY" if parser_mode == "TOOL" else "THINK_REPLY"

        think_text = (think_match.group(1).strip() if think_match else "")

        if reply_match:
            reply = reply_match.group(1).strip()

    #Raw output containing a private reasoning block
    reasoning = re.search(
        r"\[private reasoning behind that reply:\s*(.*?)\]",
        reply,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if reasoning:
        parser_mode += "+PRIVATE"

        if not think_text:
            think_text = reasoning.group(1).strip()

        reply = re.sub(
            r"\[private reasoning behind that reply:.*?\]",
            "",
            reply,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()

    # Remove leaked labels if they exist
    reply = re.sub(
        r"^REPLY:\s*",
        "",
        reply,
        flags=re.IGNORECASE
    )
    reply = re.sub(
        r"^THINK:\s*",
        "",
        reply,
        flags=re.IGNORECASE
    )
    reply = re.sub(
        r"^(assistant|user|system)\s*[:\-]?\s*",
        "",
        reply,
        flags=re.IGNORECASE,
    ).strip()

    # Last-resort safety net: never let literal tool-request syntax reach Discord, even if
    # every check above somehow missed it (e.g. an unbounded edge case in the hop loop).
    if TOOL_REQUEST_PATTERN.search(reply):
        print("WARNING: leaked TOOL:/QUERY: syntax survived to final reply — replacing with fallback.")
        reply = "Couldn't get a straight answer on that, try asking again."
        parser_mode += "+LEAK_CAUGHT"

    print(f"Parser mode: {parser_mode}")
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

    # Capture who else was @mentioned BEFORE we strip mention text out of content below
    other_mentioned_ids = [m.id for m in message.mentions if m != bot.user]

    # Strip the bot mention text out of the message before logging/sending
    content = message.content
    for mention in message.mentions:
        replacement = mention.display_name

        content = (
            content
            .replace(f"<@{mention.id}>", replacement)
            .replace(f"<@!{mention.id}>", replacement)
        )
    content = content.strip()

    if not content:
        return

    # If this message is a reply, pull in what it's replying to and prefix it onto what gets
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
    await asyncio.to_thread(log_message, channel_id, message.author.display_name, author_id, logged_text, is_creator)
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
        should_respond = await asyncio.to_thread(classify_addressed_to_bot, content)
        reason = "name_keyword+classifier=yes" if should_respond else "name_keyword+classifier=no"

    print(f"[on_message] should_respond={should_respond} reason={reason}")

    if not should_respond:
        return

    async with get_channel_lock(channel_id):
        async with message.channel.typing():
            try:
                reply, think_text = await asyncio.to_thread(
                    generate_reply,
                    channel_id,
                    logged_text,
                    )

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

        # Log the bot's own reply, plus its private reasoning behind it
        # Discord already only got the `reply` text above) so it can actually explain "why" if
        # asked later instead of having zero memory of its own reasoning.
        logged_assistant_content = reply
        if think_text:
            logged_assistant_content = f"{reply}\n[private reasoning behind that reply: {think_text}]"
        await asyncio.to_thread(
            log_message, channel_id, "Niyon", bot.user.id, logged_assistant_content, is_creator=False, role="assistant"
        )

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
