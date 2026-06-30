# Discord AI Chatbot (Ollama-powered, local llama3.2:3b)

A Discord bot that replies using a locally-hosted Ollama model
(`llama3.2:3b`). Responds when @mentioned or in DMs, and keeps short
per-channel conversation context.

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
   ollama pull llama3.2:3b
   ```
3. Start the Ollama server (often runs automatically after install, or
   start manually):
   ```
   ollama serve
   ```
   By default it listens on `http://localhost:11434`. The bot talks to
   this server — no API key needed.

**Hardware note:** `llama3.2:3b` needs roughly 3-4GB of free RAM to run
at usable speed on CPU. A GPU isn't required but will be noticeably
faster.

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
   # OLLAMA_HOST=http://localhost:11434
   # OLLAMA_MODEL=llama3.2:3b
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

## Usage

- `@YourBot <message>` in any channel it can see → AI reply
- DM the bot directly → AI reply
- Reply (Discord's reply feature) to one of the bot's own messages → AI reply, no @mention needed
- Say the bot's name ("niyon") anywhere in a message → the bot does a quick check on whether it's actually being addressed, and replies if so
- After the bot replies to you, it keeps replying to your messages in that channel for 150 seconds without needing a mention/name/reply — handy for back-and-forth conversations
- `!ping` → health check
- `!reset` → clears that channel's conversation memory (including the summary and any open conversation windows)

## Deploying so it runs 24/7

Because the model runs locally via Ollama (not a hosted API), the bot
needs to live on a machine that actually has Ollama + the model
installed and enough RAM to run it — typical free serverless/background
worker tiers (free Railway/Render plans, etc.) won't have the resources
for this, so the easiest paths are:

- **Your own always-on PC**: run `ollama serve` and `python bot.py` as
  background processes (e.g. with `tmux`, `screen`, or a systemd
  service on Linux / a scheduled task on Windows).
- **A small VPS** (e.g. Hetzner, DigitalOcean, OVH — look for ~4GB RAM
  / 2 vCPU, roughly $5-12/mo): install Ollama, pull the model, then run
  the bot the same way as locally. Open no inbound ports — the bot only
  makes outbound connections to Discord and to its own local Ollama
  instance.
- **Docker Compose** on either of the above: run an `ollama/ollama`
  container alongside a container for `bot.py`, with `OLLAMA_HOST`
  pointed at the Ollama service name (e.g. `http://ollama:11434`).

Set `DISCORD_TOKEN` (and any `OLLAMA_HOST`/`OLLAMA_MODEL` overrides) in
the host's environment variable panel or `.env` file, not in code.

## Notes

- The bot keeps the last 16 lines per channel as raw transcript (`MAX_HISTORY`)
  for immediate context. Once older messages roll out of that window, they're
  automatically folded into a short running summary per channel (using the
  same Ollama model), so the bot retains a sense of who's involved and what's
  been going on well beyond the last 16 lines — without sending the entire
  history on every request.
- Both the raw transcript and the summary are in-memory and reset when the
  bot restarts. For persistence across restarts, swap `channel_log` and
  `channel_summary` for SQLite/Redis.
- The "still talking to me" window (`CONVO_WINDOW_SECONDS`, default 150s) and
  the name keyword (`BOT_NAME_KEYWORD`, default "niyon") are both tunable
  constants near the top of `bot.py`. The only extra AI call this adds is a
  very short yes/no check, and only for messages that contain the bot's name
  but weren't an explicit mention/reply — most messages don't trigger it at all.
- `llama3.2:3b` is a small, fast model — good for casual chat, but
  noticeably weaker at reasoning/coding than larger hosted models. If
  replies feel too shallow and your hardware can handle it, try pulling
  a bigger model (`ollama pull llama3.2:8b` or similar) and setting
  `OLLAMA_MODEL` accordingly — no other code changes needed.
- Multiple concurrent Discord conversations will queue against the same
  local Ollama instance, so replies may slow down under heavier traffic
  since everything runs on one machine instead of a scaled cloud API.
- Want bigger/smarter-model answers occasionally without changing your
  whole setup? You can also point `OLLAMA_HOST` at a remote Ollama
  instance with more RAM/GPU if you have one available.
