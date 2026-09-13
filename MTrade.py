import os
import json
import uuid
from datetime import date

from dotenv import load_dotenv
from anthropic import Anthropic
import requests as http

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
DRAFT_STORE_PATH = os.environ.get("DRAFT_STORE_PATH", "./pending_drafts.json")

client = Anthropic(api_key=ANTHROPIC_API_KEY)

RESEARCH_AND_DRAFT_PROMPT = """\
You write daily Twitter/X content for MTrade, a startup building a trading
community platform. Your job today:

1. Research: find the single biggest trading-community-relevant story from
   the last 24-48 hours (market-moving news, a platform/tool change, or a
   notable shift in retail trading sentiment/community chatter).
2. Write exactly 3 tweet drafts (each under 280 characters) about it, each
   with a different angle:
   - "news_recap": a punchy factual recap with a hook question
   - "educational": a lesson or insight retail traders can take from it
   - "community_cta": frames it as a discussion starter for a trading
     community, invites replies, subtly nods to MTrade

Tone: confident, concise, no hype/emoji spam, one relevant hashtag max per
tweet. No fabricated numbers -- only use facts from your research.

Respond with ONLY valid JSON, no other text, no markdown fences:
{
  "source_summary": "1-2 sentence summary of what you found and why it matters",
  "drafts": [
    {"angle": "news_recap", "text": "..."},
    {"angle": "educational", "text": "..."},
    {"angle": "community_cta", "text": "..."}
  ]
}
"""


def research_and_draft():
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": RESEARCH_AND_DRAFT_PROMPT}],
    )

    # Concatenate all text blocks (there may be several interleaved with tool use)
    text = "".join(block.text for block in response.content if block.type == "text")

    # Claude sometimes wraps JSON in fences despite instructions -- strip defensively
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def save_pending_drafts(batch_id, drafts):
    store = {}
    if os.path.exists(DRAFT_STORE_PATH):
        with open(DRAFT_STORE_PATH, "r") as f:
            store = json.load(f)
    store[batch_id] = {d["angle"]: d["text"] for d in drafts}
    with open(DRAFT_STORE_PATH, "w") as f:
        json.dump(store, f, indent=2)


def send_telegram_approval(batch_id, source_summary, drafts):
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    intro = f"📊 *MTrade daily drafts* — {date.today().isoformat()}\n\n_{source_summary}_"
    http.post(f"{base}/sendMessage", json={
        "chat_id": 1839406333,
        "text": intro,
        "parse_mode": "Markdown",
    })

    for draft in drafts:
        angle = draft["angle"]
        text = draft["text"]
        callback_data = f"post|{batch_id}|{angle}"  # max 64 bytes, keep short
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Post this", "callback_data": callback_data},
                {"text": "⏭ Skip", "callback_data": f"skip|{batch_id}|{angle}"},
            ]]
        }
        label = angle.replace("_", " ").title()
        http.post(f"{base}/sendMessage", json={
            "chat_id": 1839406333,
            "text": f"*{label}*\n\n{text}",
            "parse_mode": "Markdown",
            "reply_markup": json.dumps(keyboard),
        })


def main():
    result = research_and_draft()
    batch_id = uuid.uuid4().hex[:8]
    save_pending_drafts(batch_id, result["drafts"])
    send_telegram_approval(batch_id, result["source_summary"], result["drafts"])
    print(f"Sent batch {batch_id} for approval.")


if __name__ == "__main__":
    main()
