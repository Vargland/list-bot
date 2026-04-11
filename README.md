# List Bot

A Telegram bot that manages a shared shopping list using voice notes and text messages. Built with Python, it transcribes voice messages using Groq's Whisper API and uses LLaMA to understand natural language.

## Features

- **Voice & text input** — send a voice note or text message with items you need to buy
- **Smart extraction** — LLaMA parses natural language to identify shopping items
- **Shared lists** — add the bot to a group so multiple people share the same list
- **User tracking** — each user registers their name; the list can show who added each item
- **Partial or total purchase** — mark specific items as bought or clear the whole list
- **Soft delete** — bought items are marked as `bought = true` in the database, never hard deleted

## Commands & phrases

| Phrase | Action |
|---|---|
| `/start` | Register your name and get started |
| `"I need milk and bread"` | Adds items to the list |
| Voice note | Transcribed and items extracted automatically |
| `"show me the list"` / `"dame la lista"` | Returns all pending items |
| `"show list with names"` / `"dame la lista con nombres"` | Returns list with who added each item |
| `"I bought everything"` / `"compré todo"` | Marks all items as bought |
| `"I bought the milk and bread"` / `"compré la leche y el pan"` | Marks specific items as bought |

## Tech stack

| Component | Technology |
|---|---|
| Bot framework | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) |
| Voice transcription | Groq Whisper (`whisper-large-v3-turbo`) |
| Natural language | Groq LLaMA (`llama-3.3-70b-versatile`) |
| Database | PostgreSQL via asyncpg |
| Hosting | Railway |

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Vargland/list-bot.git
cd list-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=your_postgresql_connection_string
```

- **Telegram bot token** — create a bot via [@BotFather](https://t.me/BotFather)
- **Groq API key** — get a free key at [console.groq.com](https://console.groq.com)
- **Database URL** — a PostgreSQL connection string (e.g. from Railway)

### 4. Run

```bash
python bot.py
```

## Deployment (Railway)

1. Push the repo to GitHub
2. Create a new project on [Railway](https://railway.app)
3. Add the repo as a service
4. Add a PostgreSQL database service
5. Set `TELEGRAM_BOT_TOKEN` and `GROQ_API_KEY` as environment variables
6. Reference `DATABASE_URL` from the Postgres service

Railway will auto-deploy on every push to `main`.

## Database schema

```sql
CREATE TABLE users (
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    name    TEXT NOT NULL,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE items (
    id       SERIAL PRIMARY KEY,
    chat_id  BIGINT NOT NULL,
    user_id  BIGINT,
    item     TEXT NOT NULL,
    bought   BOOLEAN NOT NULL DEFAULT FALSE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Using with a group

1. Create a Telegram group with the people you shop with
2. Add the bot to the group
3. Each person sends `/start` to register their name
4. Everyone shares the same list (identified by the group's `chat_id`)
