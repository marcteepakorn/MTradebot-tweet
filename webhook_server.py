"""
webhook_server.py

A small always-on Flask app that receives Telegram button-tap callbacks
and posts the approved tweet to X. Deploy this once (e.g. on Railway or
Render's free/hobby tier) and point your Telegram bot's webhook at it.

This is the ONLY part of the system that needs to run continuously --
draft_generator.py just runs once a day on a schedule.
"""

import os
import json

from flask import Flask, request, jsonify
from dotenv import load_dotenv
import tweepy
import requests as http

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DRAFT_STORE_PATH = os.environ.get("DRAFT_STORE_PATH", "./pending_drafts.json")

x_client = tweepy.Client(
    consumer_key=os.environ["X_CONSUMER_KEY"],
    consumer_secret=os.environ["X_CONSUMER_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

app = Flask(__name__)


def load_drafts():
    if not os.path.exists(DRAFT_STORE_PATH):
        return {}
    with open(DRAFT_STORE_PATH, "r") as f:
        return json.load(f)


def answer_callback(callback_query_id, text):
    http.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text},
    )


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(force=True)
    callback = update.get("callback_query")
    if not callback:
        return jsonify({"ok": True})  # ignore non-button updates

    action, batch_id, angle = callback["data"].split("|")
    callback_query_id = callback["id"]

    if action == "skip":
        answer_callback(callback_query_id, "Skipped.")
        return jsonify({"ok": True})

    drafts = load_drafts()
    batch = drafts.get(batch_id)
    if not batch or angle not in batch:
        answer_callback(callback_query_id, "Draft expired or already used.")
        return jsonify({"ok": True})

    tweet_text = batch[angle]
    try:
        x_client.create_tweet(text=tweet_text)
        answer_callback(callback_query_id, "Posted to X ✅")
        del drafts[batch_id]  # prevent double-posting the same batch
        with open(DRAFT_STORE_PATH, "w") as f:
            json.dump(drafts, f, indent=2)
    except Exception as e:
        answer_callback(callback_query_id, f"Failed: {e}")

    return jsonify({"ok": True})


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
