"""Small, reviewed bilingual reference library; never presented as a general AI."""
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata


KNOWLEDGE_PATH = Path(__file__).resolve().parent / "data" / "knowledge.json"


def language_code(language):
    return "en" if str(language).lower().split("-")[0] == "en" else "bn"


def normalize(text):
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    return " ".join(text.replace("\u200c", "").replace("\u200d", "").split())


def contains(text, phrase):
    """Latin words need boundaries: 'hi' must not match 'something'."""
    text, phrase = normalize(text), normalize(phrase)
    if phrase.isascii():
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", text))
    return phrase in text


@lru_cache(maxsize=1)
def library():
    with KNOWLEDGE_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def get_entry(topic):
    return next(item for item in library()["entries"] if item["id"] == topic)


def find_entry(message):
    """Deterministic keyword retrieval including Bangla and Banglish phrases."""
    text = normalize(message)
    best, best_score = get_entry("fallback"), 0
    for entry in library()["entries"]:
        matches = [word for word in entry["keywords"] if contains(text, word)]
        if entry["id"] == "greeting":
            matches = [word for word in matches if text.strip("!?.।, ") == normalize(word)]
        if not matches:
            continue
        # Specific phrases outrank general crop names; extra matches break ties.
        score = max(len(normalize(word)) for word in matches) + min(len(matches), 3)
        if entry["id"] in {"disease", "pests", "weather", "prices", "drainage"}:
            score += 4
        if score > best_score:
            best, best_score = entry, score
    return best


def sources_for(entry, language="bn"):
    lang = language_code(language)
    sources = library()["sources"]
    return [
        {"title": sources[key]["title"][lang], "url": sources[key]["url"]}
        for key in entry.get("sources", []) if key in sources
    ]


def knowledge_answer(message, language="bn", *, topic=None):
    lang = language_code(language)
    entry = get_entry(topic) if topic else find_entry(message)
    return {
        "text": entry["answer"][lang], "mode": "knowledge",
        "sources": sources_for(entry, lang), "topic": entry["id"],
    }
