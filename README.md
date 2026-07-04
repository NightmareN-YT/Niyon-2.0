# Niyon 2.0 — Discord AI Chatbot (Ollama-powered, local qwen2.5:7b)

A Discord bot with a defined personality ("Niyon 2.0") that replies using a
locally-hosted Ollama model (`qwen2.5:7b`). Responds when @mentioned,
in DMs, or when replied to; tracks per-channel conversation context with
automatic summarization; and recognizes its creator for a more familiar
tone.

## ⚠️ First: rotate your Discord token

If your Discord bot token was ever pasted anywhere outside your own `.env`
file or host's secret manager, treat it as compromised:

1. discord.com/developers/applications → your app → **Bot** tab
2. Click **Reset Token** → copy the new one
3. Use only the new token — never commit it or paste it in chat again

## Install Ollama and pull the model

1. Install Ollama: ollama.com/download (macOS, Windows, Linux, or
   Docker image `ollama/ollama`)
2. Pull the model:
   ```
   ollama pull qwen2.5:7b
   ```
3. Start the Ollama server (often runs automatically after install, or
   start manually):
   ```
   ollama serve
   ```
   By default it listens on `http://127.0.0.1:11434`. The bot talks to
   this server — no API key needed.

**Hardware note:** `qwen2.5:7b` is meaningfully heavier than a 3B model —
budget roughly 6-8GB of free RAM to run it at usable speed on CPU. A GPU
isn't required but will be noticeably faster, especially given the large
reply token budget this bot uses (see Notes below).

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Create your `.env` file** (copy `env.example.txt`, rename to `.env`,
   fill in real values):
   ```
   DISCORD_TOKEN=your_new_reset_discord_bot_token
   # Optional overrides (defaults shown):
   # CREATOR_USERNAME=niyon9
   # OLLAMA_HOST=http://127.0.0.1:11434
   # OLLAMA_MODEL=qwen2.5:7b
   ```
   `.gitignore` already excludes `.env` — never commit it.

3. **Enable the Message Content Intent**
   Discord Developer Portal → your app → Bot tab → "Privileged Gateway
   Intents" → toggle ON **Message Content Intent**.

4. **Invite the bot to your server**
   Developer Portal → OAuth2 → URL Generator → scopes: `bot` →
   permissions: at least `Send Messages`, `Read Message History` →
   open the generated URL and add it to your server.

5. **Run locally** (for testing):
   ```
   export $(cat .env | xargs)   # Mac/Linux
   python bot.py
   ```
   On Windows PowerShell, `.env` isn't loaded automatically — set the
   token for the session first:
   ```powershell
   $env:DISCORD_TOKEN = "your_token_here"
   python bot.py
   ```

## Usage

- `@YourBot <message>` in any channel it can see → AI reply. The mention is
  replaced with the mentioned user's display name in what the model sees
  (so it reads as natural text, e.g. "Niyon what do you think" rather than
  a raw mention token).
- DM the bot directly → AI reply
- Reply (Discord's reply feature) to one of the bot's own messages → AI reply, no @mention needed
- Say the bot's name ("niyon") anywhere in a message → the bot does a quick check on whether it's actually being addressed, and replies if so
- After the bot replies to you, it keeps replying to your messages in that channel for 150 seconds without needing a mention/name/reply — handy for back-and-forth conversations
- Reply to someone else's message while talking to the bot → the bot sees what you were replying to, so it has context instead of just your message in isolation
- Ask it to ping/mention/greet/tag someone (including yourself) → it inserts a real Discord mention, resolved deterministically rather than left to the model to get right
- `!ping` → health check
- `!reset` → clears that channel's conversation memory (including the summary and any open conversation windows)

## Personality

The bot has a fixed personality ("Niyon 2.0"): terse, direct, low-filler,
with a bit of an edge — not a generic helpful-assistant tone. It's defined
entirely in the `SYSTEM_PROMPT` constant near the top of `bot.py`; edit
that string to change how it talks.

Messages from the user whose Discord username matches `CREATOR_USERNAME`
(default `niyon9`, override via env var) are tagged `[CREATOR]` internally,
and the personality prompt treats that user with more familiarity and is
more willing to go into real technical detail about the bot's own code/prompt
when talking with them specifically.

## Notes

- The bot keeps the last **48** messages per channel as proper conversation
  turns (each tagged `user` or `assistant`, not flattened into one text
  blob), so it reliably tracks its own previous replies and stays anchored
  to the actual last message instead of drifting into unrelated responses.
  Once older messages roll out of that window, they're automatically folded
  into a short running summary per channel (using the same Ollama model), so
  the bot retains a sense of who's involved and what's been going on well
  beyond the last 48 messages — without sending the entire history on every
  request.
- Replies are meant to follow a `THINK:` / `REPLY:` format internally, but
  the parser is more permissive than a strict format check: it looks for a
  `THINK:`/`REPLY:` pair first, falls back to stripping a
  `[private reasoning behind that reply: ...]` block if the model echoes one
  back, and strips any leaked `REPLY:`/`THINK:`/role labels either way — so
  a reply still gets sent even if the model doesn't follow the format
  exactly. The console log for each reply prints which `Parser mode` was
  used, which is worth checking if replies look malformed. Only the final
  `REPLY:` text is ever sent to Discord — the `THINK:` reasoning is kept in
  the bot's own memory of the conversation (not shown to users) so it can
  give a real answer if later asked why it said something.
- Both the raw transcript and the summary are in-memory and reset when the
  bot restarts. For persistence across restarts, swap `channel_log` and
  `channel_summary` for SQLite/Redis.
- The "still talking to me" window (`CONVO_WINDOW_SECONDS`, default 150s),
  the name keyword (`BOT_NAME_KEYWORD`, default "niyon"), history length
  (`MAX_HISTORY`, default 48), and the per-reply generation cap
  (`MAX_REPLY_TOKENS`, default **4096**) are all tunable constants near the
  top of `bot.py`. That token cap is intentionally generous headroom for
  `qwen2.5:7b`'s THINK+REPLY output — expect noticeably longer per-reply
  latency than a smaller model/tighter cap would give you, especially on
  CPU. The name-keyword path's extra AI call is a very short yes/no check,
  and only fires for messages that contain the bot's name but weren't an
  explicit mention/reply — most messages don't trigger it at all.
- `qwen2.5:7b` is noticeably heavier than `llama3.2:3b` — better
  reasoning/instruction-following, but slower per reply and more RAM-hungry.
  If your hardware can't keep up, drop to a smaller model
  (`ollama pull llama3.2:3b` or similar) and set `OLLAMA_MODEL` accordingly
  — no other code changes needed, though you may want to lower
  `MAX_REPLY_TOKENS` back down too.
- The Ollama client is configured with a 240-second timeout
  (`OllamaClient(..., timeout=240)`), reflecting the heavier model and large
  reply budget — a single generation is allowed to take up to 4 minutes
  before the call is treated as failed.
- All Ollama calls (`generate_reply`, `classify_addressed_to_bot`,
  `update_summary`) run synchronously on the bot's single event loop. A slow
  or backed-up Ollama response blocks the whole bot — including the Discord
  gateway heartbeat — until it returns. Given the larger model and 4096-token
  cap here, this is worth watching closely: under heavy load, a slow
  response can cause enough delay to trigger a gateway reconnect, which
  looks like the bot silently not responding.
- Multiple concurrent Discord conversations will queue against the same
  local Ollama instance, so replies may slow down under heavier traffic
  since everything runs on one machine instead of a scaled cloud API.
- Want a different model without changing your whole setup? You can also
  point `OLLAMA_HOST` at a remote Ollama instance with more RAM/GPU if you
  have one available.

## Deployment

Because the model runs locally via Ollama (not a hosted API), the bot
needs to live on a machine that actually has Ollama + the model
installed and enough RAM to run it — typical free serverless/background
worker tiers (free Railway/Render plans, etc.) won't have the resources
for this, so the easiest paths are:

- **Your own always-on PC**: run `ollama serve` and `python bot.py` as
  background processes (e.g. with `tmux`, `screen`, or a systemd
  service on Linux / a scheduled task on Windows).
- **A small-to-medium VPS** (e.g. Hetzner, DigitalOcean, OVH — given
  `qwen2.5:7b`'s footprint, look for at least ~8GB RAM / 4 vCPU): install
  Ollama, pull the model, then run the bot the same way as locally. Open no
  inbound ports — the bot only makes outbound connections to Discord and to
  its own local Ollama instance.
- **Docker Compose** on either of the above: run an `ollama/ollama`
  container alongside a container for `bot.py`, with `OLLAMA_HOST`
  pointed at the Ollama service name (e.g. `http://ollama:11434`).

Set `DISCORD_TOKEN` (and any `CREATOR_USERNAME`/`OLLAMA_HOST`/`OLLAMA_MODEL`
overrides) in the host's environment variable panel or `.env` file, not in
code.
