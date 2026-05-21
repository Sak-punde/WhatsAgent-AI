"""Adjective selection — one word sent per day from a fixed list."""

from __future__ import annotations

import logging
from typing import Any

from config import Config
from utils import load_json, save_json, utc_now_iso

logger = logging.getLogger("identity_agent")

class AdjectiveEngine:
    """
    Loads a list of one-word messages (fantastic, great, amazing, ...).

    Sends the next word from the list each day, in A-Z order.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._answers: list[str] = []
        self._load_answers()

    @staticmethod
    def _is_single_word(word: str) -> bool:
        """Plain one word: letters only, e.g. fantastic, great."""
        w = word.strip().lower()
        return bool(w) and w.isalpha() and 3 <= len(w) <= 12

    def _load_answers(self) -> None:
        """Load one-word list from how_are_you_answers.json or adjectives.json."""
        # Prefer curated answer list
        answer_data = load_json(
            self.config.how_are_you_answers_path,
            default={"answers": []},
        )
        answers = answer_data.get("answers", [])

        if not answers:
            # Fallback: filter main adjective file
            data = load_json(
                self.config.adjectives_path,
                default={"adjectives": [], "categories": {}},
            )
            answers = data.get("adjectives", [])
            if not answers and "categories" in data:
                seen: set[str] = set()
                answers = []
                for words in data["categories"].values():
                    for word in words:
                        w = word.strip().lower()
                        if w and w not in seen:
                            seen.add(w)
                            answers.append(w)

        self._answers = sorted(
            {
                a.strip().lower()
                for a in answers
                if self._is_single_word(a)
            }
        )

        if not self._answers:
            raise FileNotFoundError(
                "No answer words found. Check data/how_are_you_answers.json"
            )

        logger.debug("Loaded %d words (A-Z, one per day)", len(self._answers))

    def _load_used(self) -> dict[str, Any]:
        """Load used answers tracking file."""
        return load_json(
            self.config.used_adjectives_path,
            default={"used": [], "last_reset": None},
        )

    def _save_used(self, data: dict[str, Any]) -> None:
        """Persist used answers tracking."""
        save_json(self.config.used_adjectives_path, data)

    def get_next_answer(self) -> str:
        """
        Next one-word answer from the list (sequential, no repeat until list ends).

        Example: fantastic, then great, then amazing, ...
        """
        used_data = self._load_used()
        used_set = set(used_data.get("used", []))

        for word in self._answers:
            if word not in used_set:
                used_data.setdefault("used", []).append(word)
                self._save_used(used_data)
                n = len(used_set) + 1
                logger.info('Today\'s word: "%s"  (%d/%d in list)', word, n, len(self._answers))
                return word

        logger.info(
            "All %d answers sent — restarting from '%s'",
            len(self._answers),
            self._answers[0],
        )
        used_data = {"used": [], "last_reset": utc_now_iso()}
        word = self._answers[0]
        used_data["used"] = [word]
        self._save_used(used_data)
        logger.info('Today\'s word: "%s"  (1/%d in list)', word, len(self._answers))
        return word

    def get_list_status(self) -> dict[str, Any]:
        """List progress and next answer."""
        used_data = self._load_used()
        used_set = set(used_data.get("used", []))
        next_word = next((w for w in self._answers if w not in used_set), None)
        return {
            "total": len(self._answers),
            "sent": len(used_set),
            "remaining": len(self._answers) - len(used_set),
            "next_word": next_word,
            "words": self._answers,
            "used": used_data.get("used", []),
        }

    def generate_message(self) -> str:
        """One word only — e.g. fantastic, great, amazing."""
        answer = self.get_next_answer().strip().lower()
        answer = answer.split()[0] if answer else answer
        if not answer or not answer.isalpha():
            raise ValueError(f"Invalid answer word: {answer!r}")
        self._record_history(answer, answer)
        return answer

    def _record_history(self, message: str, adjective: str) -> None:
        """Append sent answer to history."""
        history = load_json(
            self.config.message_history_path,
            default={"messages": []},
        )
        history.setdefault("messages", []).append(
            {
                "timestamp": utc_now_iso(),
                "adjective": adjective,
                "message": message,
            }
        )
        history["messages"] = history["messages"][-365:]
        save_json(self.config.message_history_path, history)

    @property
    def total_adjectives(self) -> int:
        """Total answers in list."""
        return len(self._answers)

    @property
    def remaining_count(self) -> int:
        """Answers not yet sent this cycle."""
        used_data = self._load_used()
        used_set = set(used_data.get("used", []))
        return len([a for a in self._answers if a not in used_set])
