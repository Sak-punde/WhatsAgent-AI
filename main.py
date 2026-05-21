"""
WhatsApp Identity Agent — main entry point.

Sends one unique adjective-based identity message daily via WhatsApp Web.
"""

from __future__ import annotations

import argparse
import sys

from adjective_engine import AdjectiveEngine
from config import get_config
from logger_config import setup_logging
from scheduler import DailyScheduler
from whatsapp_agent import WhatsAppAgent


def run_daily_job() -> None:
    """Generate message and send via WhatsApp."""
    config = get_config()
    log = setup_logging(config.logs_dir)
    engine = AdjectiveEngine(config)
    agent = WhatsAppAgent(config)

    message = engine.generate_message()
    log.info("Sending one word: %s", message)
    log.info(
        "Adjectives remaining this cycle: %d / %d",
        engine.remaining_count,
        engine.total_adjectives,
    )

    success = agent.run_send_flow(config.target_contact_name, message)
    if not success:
        log.error("Failed to send message — check logs and screenshots/")
        sys.exit(1)


def main() -> None:
    """Parse CLI args and start agent."""
    parser = argparse.ArgumentParser(
        description="WhatsApp Identity Agent — daily adjective messages",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Send message immediately instead of waiting for schedule",
    )
    parser.add_argument(
        "--schedule-only",
        action="store_true",
        help="Only run scheduler without immediate send",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show the full adjective list and which word is next",
    )
    args = parser.parse_args()

    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("Copy .env.example to .env and fill in your settings.")
        sys.exit(1)

    log = setup_logging(config.logs_dir)

    if args.list:
        engine = AdjectiveEngine(config)
        status = engine.get_list_status()
        print(f'\nOne word per day ({status["total"]} words, A-Z order)\n')
        print(f"Already sent: {status['sent']}  |  Remaining: {status['remaining']}")
        if status["next_word"]:
            print(f'Next answer to send: "{status["next_word"]}"\n')
        used_set = set(status["used"])
        for i, word in enumerate(status["words"], start=1):
            mark = "[x]" if word in used_set else "[ ]"
            nxt = " <-- NEXT" if word == status["next_word"] else ""
            print(f"  {i:4}. {mark} {word}{nxt}")
        print()
        return

    log.info("Identity Agent started")
    log.info("Target: %s | Send time: %s", config.target_contact_name, config.send_time)

    if args.now:
        run_daily_job()
        return

    scheduler = DailyScheduler(config, run_daily_job)
    scheduler.setup()

    if not args.schedule_only:
        log.info("Tip: use --now to send immediately without waiting")

    scheduler.run_forever()


if __name__ == "__main__":
    main()
