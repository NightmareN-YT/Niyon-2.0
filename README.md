# Discord AI Chatbot (Gemini-powered)

A Discord bot that replies using the free Google Gemini API. Responds when
@mentioned or in DMs, and keeps short per-channel conversation context.

## ⚠️ First: rotate your Discord token

If your Discord bot token was ever pasted anywhere outside your own `.env`
file or host's secret manager, treat it as compromised:

1. discord.com/developers/applications → your app → **Bot** tab
2. Click **Reset Token** → copy the new one
3. Use only the new token — never commit it or paste it in chat again

## Get a free Gemini API key

1. Go to **aistudio.google.com**
2. Sign in with a Google account → click **Get API key** → **Create API key**
3. Copy it — this is your `GEMINI_API_KEY`

The free tier (via Google AI Studio) has no expiration and a generous daily
quota for `gemini-2.5-flash`, no credit card required.

## Setup

1. **Install dependencies**
   ```
   pip install -r requirements.txt
   ```

2. **Create your `.env` file** (copy `env.example.txt`, rename to `.env`,
   fill in real values):
   ```
   DISCORD_TOKEN=your_new_reset_discord_bot_token
   GEMINI_API_KEY=your_gemini_api_key
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
- `!ping` → health check
- `!reset` → clears that channel's conversation memory

## Deploying so it runs 24/7

Push this folder to a GitHub repo, then connect it to a host that
auto-deploys from GitHub and supports background workers:

- **Railway** (easiest): New Project → Deploy from GitHub repo → add
  `DISCORD_TOKEN` and `GEMINI_API_KEY` as environment variables in the
  Variables tab → it auto-deploys on every push.
- **Render**: New → Background Worker → connect repo → set the same env
  vars → start command `python bot.py`.

Set secrets in the **host's** environment variable panel, not in code or
a committed `.env`.

## Notes

- Conversation history is in-memory and resets when the bot restarts. For
  persistence, swap the `history` dict for SQLite/Redis.
- Free-tier rate limits on `gemini-2.5-flash` are generous (roughly
  15 requests/min, 1,500/day as of mid-2026) but can change — check
  ai.google.dev/pricing if the bot starts erroring on quota.
- Want Opus/Claude-quality answers occasionally? You can swap `MODEL` to
  `gemini-2.5-pro` for tougher questions, with lower free-tier limits.
