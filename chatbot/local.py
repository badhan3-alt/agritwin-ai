"""Deterministic on-device conversation over the bundled farming references.

No model, network request, API key, training download or extra package is used.
Only recent user messages help interpret short follow-ups; retrieved text never
becomes an instruction. A fresh question does not inherit unrelated farm facts.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from difflib import get_close_matches
import re
from urllib.parse import urlsplit, urlunsplit

from .knowledge import contains, find_entry, get_entry, language_code, normalize, sources_for


MAX_MESSAGE = 2000
MAX_HISTORY = 8
_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
_EN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
CROPS = {
    "rice": {"bn": "ধান", "en": "rice", "words": ("ধান", "rice", "paddy", "dhan", "boro", "aman", "aus", "বোরো", "আমন", "আউশ")},
    "potato": {"bn": "আলু", "en": "potato", "words": ("আলু", "potato", "potatoes", "alu")},
    "tomato": {"bn": "টমেটো", "en": "tomato", "words": ("টমেটো", "টমেটা", "tomato", "tomatoes", "tometo")},
    "wheat": {"bn": "গম", "en": "wheat", "words": ("গম", "wheat", "gom")},
    "maize": {"bn": "ভুট্টা", "en": "maize", "words": ("ভুট্টা", "maize", "corn", "bhutta", "vutta")},
    "jute": {"bn": "পাট", "en": "jute", "words": ("পাট", "jute", "pat chash")},
    "pulses": {"bn": "ডাল", "en": "pulses", "words": ("মসুর", "মুগ", "মাষ", "ডাল", "lentil", "lentils", "mung", "pulse", "pulses", "masur", "mosur", "mug dal")},
}
_EXTRA_INTENTS = {
    "irrigation": ("কখন পানি", "পানি কখন", "জল দেব", "পানি দিতে", "water should", "water do", "water need", "water", "irrigate", "pani kokhon", "pani kobe"),
    "soil": ("মাটির যত্ন", "মাটির মান", "মাটির গুণ", "মাটির উর্বর", "soil", "soil health", "soil care", "mati test"),
    "fertilizer": ("সার দেব", "সার দিতে", "সার লাগবে", "সারের পরিমাণ", "সার কত", "sar koto", "sar debo", "fertilization"),
    "pests": ("পোকা", "কীট", "কীটনাশক", "পোকামাকড়", "insects", "pests", "poka hoise"),
    "disease": ("রোগ", "পাতা হলুদ", "শুকিয়ে", "শুকিয়ে", "পচে", "দাগ", "পচন", "পাতা কুঁকড়ে", "পাতা কুঁকড়ে", "spots", "yellowing", "wilts", "rotting", "পাতা নষ্ট"),
    "sowing": ("কখন লাগাব", "কখন বুনব", "কখন চাষ", "বীজ বুন", "রোপণ", "বপন", "বীজতলা", "when to grow", "when to sow", "when to plant", "বীজ লাগাব", "bij bunbo"),
    "rotation": ("after rice", "plant after", "grow after", "crop after", "ধানের পর", "ধানের পরে", "ফসলের পরে", "পরবর্তী ফসল"),
    "drainage": ("জলাবদ্ধ", "পানি জমে", "পানিতে ডুবে", "জমিতে পানি জম", "waterlogged", "flooded"),
    "storage": ("সংরক্ষণ", "গুদাম", "কেটে রাখ", "মজুত", "store", "harvest storage"),
    "compost": ("কম্পোস্ট", "জৈব সার", "গোবর", "joibo sar", "composting"),
}
_FOLLOWUPS = (
    "আরও", "আরো", "আরও বলুন", "আরো বলুন", "বিস্তারিত", "তারপর", "এরপর", "কখন", "কতদিন পর", "কীভাবে", "কিভাবে", "কেন",
    "আর কী", "কি করব", "কী করব", "এখন কী করব", "হ্যাঁ", "আচ্ছা", "আরও বিস্তারিত",
    "more", "tell me more", "more details", "more details please", "what next", "then", "when", "how", "why", "yes", "okay", "ok",
    "for it", "what about it", "next step", "aro bolun", "ar ki", "erpor", "kokhon", "kivabe",
)
_RESET = ("নতুন প্রশ্ন", "নতুন করে শুরু", "শুরু থেকে", "আবার শুরু", "new question", "start over", "reset", "not that")
_THANKS = ("ধন্যবাদ", "অনেক ধন্যবাদ", "ধন্যবাদ আপনাকে", "thanks", "thank you", "thank you very much", "dhonnobad", "dhonyobad")
_IDENTITY = ("তুমি কে", "আপনি কে", "তোমার নাম", "আপনার নাম", "who are you", "your name", "are you ai", "কি বট", "কী বট", "tumi ke")
_CARE = ("চাষ", "পরিচর্যা", "যত্ন", "care", "grow", "growing", "cultivation", "chash", "chas")


def _text(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()[:MAX_MESSAGE]


def _bare(value):
    return normalize(value).strip("!?.।, \t\n")


def _any(text, words):
    return any(contains(text, word) for word in words)


def _digits(value, lang):
    return str(value).translate(_BN_DIGITS) if lang == "bn" else str(value)


def _reply(text, topic, lang, *, sources=True):
    references = []
    if sources:
        try:
            references = sources_for(get_entry(topic), lang)
        except StopIteration:
            references = sources_for(get_entry("help"), lang)
        # The bundled market/storage reference may use presentation queries.
        # Their public pages work without those queries, and keep source links
        # within the interface's strict reviewed-link policy.
        references = [{**item, "url": urlunsplit((*urlsplit(item["url"])[:3], "", ""))} for item in references]
    return {"text": text, "mode": "local", "topic": topic, "sources": references}


def _crop(text):
    for crop, data in CROPS.items():
        if _any(text, data["words"]):
            return crop
    return None


def _district(text):
    # Importing the public offline catalog does not query farm records.
    from farms.regions import REGIONS, REGION_ALIASES
    for region in REGIONS:
        words = [region["district"], region["district_bn"], region["id"].replace("_", " ")]
        words.extend(alias for alias, canonical in REGION_ALIASES.items() if canonical == region["id"])
        if _any(text, words):
            return {"bn": region["district_bn"], "en": region["district"]}
    return None


def _stage(text, lang):
    text = text.translate(_EN_DIGITS)
    age = re.search(r"(?<!\d)(\d{1,3})\s*(দিন|দিনের|days?|weeks?|সপ্তাহ)(?![a-z])", text, re.I)
    if age and 0 < int(age.group(1)) <= 365:
        weeks = age.group(2).casefold() in {"সপ্তাহ", "week", "weeks"}
        unit = ("সপ্তাহ" if weeks else "দিন") if lang == "bn" else ("weeks" if weeks else "days")
        return f"{_digits(age.group(1), lang)} {unit}"
    stages = (
        (("চারা", "seedling", "seedlings"), "চারা পর্যায়", "seedling stage"),
        (("ফুল", "flowering"), "ফুল আসার পর্যায়", "flowering stage"),
        (("ফল ধর", "fruiting"), "ফল ধরার পর্যায়", "fruiting stage"),
        (("কাটা", "harvest stage", "harvesting"), "ফসল কাটার পর্যায়", "harvest stage"),
    )
    for words, bn, en in stages:
        if _any(text, words):
            return bn if lang == "bn" else en
    return None


def _topic(text):
    entry = find_entry(text)
    # Avoid a crop name such as "rice" outranking a real care question.
    for topic in ("drainage", "pests", "disease", "fertilizer", "rotation", "sowing", "irrigation", "soil", "storage", "compost"):
        if _any(text, _EXTRA_INTENTS[topic]):
            return topic
    if entry["id"] not in {"fallback", "rice", "rotation"}:
        return entry["id"]
    # A pulse name alone describes a crop, not a request for crop rotation.
    if entry["id"] == "rotation" and _any(text, ("rotation", "rotate", "sequence", "পর্যায়ক্রম", "পর্যায়ক্রম", "বিন্যাস", "ফসল বদল", "fosol bodol")):
        return "rotation"
    # Tolerate a small typo in a long English topic word without fuzzy
    # matching arbitrary user prose or short words like "hi".
    words = re.findall(r"[a-z]{7,24}", normalize(text))[:24]
    aliases = {"irrigation": "irrigation", "fertilizer": "fertilizer", "fertiliser": "fertilizer", "composting": "compost", "waterlogging": "drainage", "transplanting": "sowing"}
    for word in words:
        match = get_close_matches(word, aliases, n=1, cutoff=0.87)
        if match:
            return aliases[match[0]]
    return None


def _short_followup(text):
    if len(text) > 140:
        return False
    if _bare(text) in _FOLLOWUPS:
        return True
    if not (_crop(text) or _district(text) or _stage(text, "en")):
        return False
    # Accept requested values and simple declarations, not any sentence that
    # happens to mention a district/crop ("Why is the sky blue in Dhaka?").
    from farms.regions import REGIONS, REGION_ALIASES
    remainder = normalize(text).translate(_EN_DIGITS)
    names = [word for data in CROPS.values() for word in data["words"]]
    names += [word for region in REGIONS for word in (region["district"], region["district_bn"], region["id"].replace("_", " "))]
    names += list(REGION_ALIASES)
    for name in sorted(names, key=len, reverse=True):
        name = normalize(name)
        if name.isascii():
            remainder = re.sub(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", " ", remainder)
        else:
            remainder = re.sub(re.escape(name) + r"(?:ের|য়ের|য়ের|য়|য়|তে|র|ে)?", " ", remainder)
    fillers = (
        "আমার", "আমাদের", "ফসল", "জেলা", "জেলার", "জেলায়", "জেলায়", "বয়স", "বয়স", "দিনের", "দিন", "সপ্তাহ", "পর্যায়ে", "পর্যায়", "চারা", "ফুল", "ফল", "ধরার", "বছর", "জমি", "ক্ষেত", "আছে", "হয়েছে", "হয়েছে",
        "my", "our", "crop", "is", "it", "in", "i", "grow", "district", "from", "age", "aged", "old", "days", "day", "weeks", "week", "and", "the", "stage", "seedling", "seedlings", "flowering", "fruiting",
    )
    for word in sorted(fillers, key=len, reverse=True):
        if word.isascii():
            remainder = re.sub(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", " ", remainder)
        else:
            remainder = remainder.replace(normalize(word), " ")
    return not re.search(r"[a-z\u0980-\u09df]", remainder)


def _topic_followup(text, topic):
    related = {"care", "irrigation", "soil", "fertilizer", "disease", "pests", "sowing", "storage", "drainage"}
    if topic not in related or len(text) > 60:
        return False
    bare = _bare(text)
    prefixes = ("what about ", "about ", "আর ")
    for prefix in prefixes:
        if bare.startswith(prefix):
            bare = bare[len(prefix):].strip()
    try:
        words = list(get_entry(topic)["keywords"]) + list(_EXTRA_INTENTS.get(topic, ()))
    except StopIteration:
        return False
    return any(bare == _bare(word) for word in words)


def _recent_state(history):
    state = {"topic": None, "crop": None, "district": None, "stage": None}
    if not isinstance(history, (tuple, list)):
        return state
    for item in history[-MAX_HISTORY:]:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        text = _text(item.get("content", item.get("body")))
        if not text:
            continue
        if _bare(text) in _RESET:
            state = dict.fromkeys(state)
            continue
        topic, crop = _topic(text), _crop(text)
        if topic:
            # A fresh, explicit topic begins a new context. Crops/districts
            # are retained only for short answers to a previous question.
            if state["topic"] and _topic_followup(text, topic):
                previous_crop = state["crop"]
                state = {"topic": topic, "crop": crop or previous_crop, "district": _district(text) or state["district"], "stage": text if _stage(text, "en") else (state["stage"] if not crop or crop == previous_crop else None)}
            else:
                state = {"topic": topic, "crop": crop, "district": _district(text), "stage": text if _stage(text, "en") else None}
        elif _short_followup(text) and state["topic"]:
            if crop and crop != state["crop"]:
                state["crop"], state["stage"] = crop, None
            state["district"] = _district(text) or state["district"]
            if _stage(text, "en"):
                state["stage"] = text
        elif crop:
            state = {"topic": "care", "crop": crop, "district": _district(text), "stage": text if _stage(text, "en") else None}
        else:
            # Unrecognized full questions must not revive old crop advice.
            state = dict.fromkeys(state)
    return state


def _farm_crop(context):
    if not isinstance(context, dict) or not isinstance(context.get("farm"), dict):
        return None
    values = context["farm"].get("crops")
    if not isinstance(values, (list, tuple)):
        return None
    known = {_crop(_text(value)) for value in values[:12]}
    known.discard(None)
    return next(iter(known)) if len(known) == 1 else None


def _conversion(text, lang):
    latin = normalize(text).translate(_EN_DIGITS)
    units = r"acres?|hectares?|একর|হেক্টর"
    match = re.fullmatch(rf"(?:convert\s+)?(\d{{1,7}}(?:\.\d{{1,6}})?)\s*({units})\s*(?:to|in|into|কত|কতো|সমান|=|থেকে)\s*({units})[?।.\s]*", latin)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:
        return None
    source_acre = match.group(2).startswith("acre") or match.group(2) == "একর"
    target_acre = match.group(3).startswith("acre") or match.group(3) == "একর"
    if source_acre == target_acre:
        value = amount
    else:
        factor = Decimal("0.40468564224")
        value = amount * factor if source_acre else amount / factor
    value = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    value_text = format(value, "f").rstrip("0").rstrip(".") or "0"
    if lang == "bn":
        source, target = ("একর" if source_acre else "হেক্টর"), ("একর" if target_acre else "হেক্টর")
        text = f"{_digits(amount, lang)} {source} ≈ {_digits(value_text, lang)} {target}। ফল চার দশমিক স্থান পর্যন্ত দেখানো হয়েছে। বিঘার আকার এলাকাভেদে বদলায়, তাই এখানে বিঘা ধরে হিসাব করা হয়নি।"
    else:
        source, target = ("acres" if source_acre else "hectares"), ("acres" if target_acre else "hectares")
        text = f"{amount} {source} ≈ {value_text} {target}. Rounded to four decimal places. Bigha sizes vary by locality, so no bigha conversion is assumed."
    return _reply(text, "conversion", lang, sources=False)


def _care_question(crop, lang):
    questions = {
        "rice": ("আউশ, আমন না বোরো ধান? জাতের নাম, বয়স ও জেলা কী?", "Is this Aus, Aman or Boro rice? What are the variety, crop age and district?"),
        "potato": ("আলুর জাত, রোপণের সময় ও জেলা কী? পাতায় নাকি কন্দে সমস্যা?", "What potato variety, planting time and district? Is the concern on leaves or tubers?"),
        "tomato": ("টমেটো এখন বীজতলায়, রোপণের পরে নাকি ফল ধরার পর্যায়ে? জেলা কী?", "Are the tomatoes in a nursery, transplanted, or fruiting? What is the district?"),
        "wheat": ("গমের জাত, বপনের সময় ও জেলা কী?", "What are the wheat variety, sowing time and district?"),
        "maize": ("ভুট্টা রবি না খরিফ মৌসুমের? বয়স ও জেলা কী?", "Is the maize a Rabi or Kharif crop? What are its age and district?"),
        "jute": ("দেশি না তোষা পাট? বপনের সময়, বয়স ও জেলা কী?", "Is this deshi or tossa jute? What are its sowing time, age and district?"),
        "pulses": ("কোন ডাল—মসুর, মুগ, মাষ নাকি অন্যটি? বয়স ও জেলা কী?", "Which pulse—lentil, mung, black gram, or another? What are its age and district?"),
    }
    return questions[crop][0 if lang == "bn" else 1]


def _checklist(topic, crop, lang):
    bn = lang == "bn"
    labels = {
        "rice": ("পাতা, কাণ্ড ও শীষ", "leaves, stems and panicles"),
        "potato": ("পাতা, কাণ্ড ও কন্দ", "leaves, stems and tubers"),
        "tomato": ("পাতা, কাণ্ড ও ফল", "leaves, stems and fruit"),
        "wheat": ("পাতা, কাণ্ড ও শীষ", "leaves, stems and ears"),
        "maize": ("পাতা, কাণ্ড ও মোচা", "leaves, stems and cobs"),
        "jute": ("পাতা, কাণ্ড ও মূল", "leaves, stems and roots"),
        "pulses": ("পাতা, কাণ্ড ও শুঁটি", "leaves, stems and pods"),
    }
    if topic in {"disease", "pests"}:
        parts = labels[crop][0 if bn else 1] if crop else ("পাতা, কাণ্ড ও মূল" if bn else "leaves, stems and roots")
        return (
            f"• {parts} পরীক্ষা করে কোন অংশে পরিবর্তন আছে লিখুন।\n• কবে শুরু হয়েছে ও কতটা জমিতে ছড়িয়েছে লিখে রাখুন।\n• সাম্প্রতিক সেচ ও সার ব্যবহারের তথ্য এবং পরিষ্কার ছবি নিয়ে কৃষি কর্মকর্তাকে দেখান।\nলক্ষণ থেকে নিশ্চিত রোগ বা কীটনাশকের মাত্রা বলা যায় না।"
            if bn else f"• Check the {parts} and note which parts changed.\n• Record when it began and how widely it has spread.\n• Take clear photos and recent watering/fertilizer records to an extension officer.\nSymptoms alone do not establish a diagnosis or a pesticide dose."
        )
    if topic == "irrigation":
        base = (
            "• সেচের আগে মাটির আর্দ্রতা, জমিতে পানি আছে কি না ও ফসলের পর্যায় দেখুন।\n• শেষ সেচের সময় লিখে রাখুন এবং অতিরিক্ত পানি বের হওয়ার পথ পরীক্ষা করুন।\n• নির্দিষ্ট বিরতি ধরে পানি না দিয়ে মাঠের অবস্থা অনুযায়ী স্থানীয় পরামর্শ নিন।"
            if bn else "• Check field moisture, any standing water and crop stage before irrigating.\n• Record the last irrigation and inspect drainage.\n• Use field conditions and local advice rather than one fixed interval for every crop."
        )
        if crop == "rice":
            base += (
                "\nউপযুক্ত সেচযুক্ত নিচু ধানজমিতে পর্যায়ক্রমে ভেজানো ও শুকানোর পদ্ধতি কাজে আসতে পারে। আগে কৃষি কর্মকর্তার কাছে জমির উপযোগিতা ও পানির স্তর মাপা শিখুন।"
                if bn else "\nAlternate wetting and drying can help in suitable irrigated lowland rice. First ask an extension officer to assess suitability and demonstrate water-level monitoring."
            )
        return base
    if topic == "fertilizer":
        return (
            "• মাটি পরীক্ষার ফল ও সুপারিশ কার্ড দেখুন।\n• ফসলের জাত, বয়স, জমির আয়তন এবং আগে দেওয়া সার লিখে রাখুন।\n• শুধু পাতা হলুদ দেখে ইউরিয়া বাড়াবেন না; কারণ যাচাই করান।\nএই তথ্য ছাড়া সারের নির্ভরযোগ্য মাত্রা হিসাব করা যাবে না।"
            if bn else "• Use the soil-test result and recommendation card.\n• Note crop variety, age, field area and fertilizer already applied.\n• Do not add urea solely because leaves are yellow; check the cause.\nA reliable dose cannot be calculated without these details."
        )
    if topic == "sowing":
        return (
            "• জেলা, ফসলের জাত ও আগের ফসল কাটার সময় মিলিয়ে পরিকল্পনা করুন।\n• স্থানীয় ফসল পঞ্জিকা ও জমির পানি নিষ্কাশনের অবস্থা দেখুন।\n• তারিখ ঠিক করার আগে উপজেলা কৃষি অফিসের এলাকার উপযোগী পরামর্শ নিন।\nএকই বপন বা রোপণের তারিখ সব জমির জন্য প্রযোজ্য নয়।"
            if bn else "• Plan around district, variety and the previous crop's harvest.\n• Check the local crop calendar and field drainage.\n• Confirm an appropriate planting window with the upazila agriculture office.\nOne sowing or transplanting date does not suit every field."
        )
    if topic == "care":
        return (
            "শুরু করার জন্য এই বিষয়গুলো দেখুন:\n• ফসলের জাত, বয়স ও মৌসুম লিখে রাখুন।\n• মাটি পরীক্ষার ভিত্তিতে সার এবং মাঠের আর্দ্রতা দেখে সেচ পরিকল্পনা করুন।\n• নিয়মিত পাতার দুই পিঠ, কাণ্ড ও জমির অবস্থা দেখুন।\nআপনি সেচ, সার, বপন, রোগ-পোকা নাকি সংরক্ষণ নিয়ে জানতে চান?"
            if bn else "Start with this checklist:\n• Record crop variety, age and season.\n• Plan fertilizer from soil-test advice and irrigation from field moisture.\n• Inspect both leaf surfaces, stems and field conditions regularly.\nWould you like help with irrigation, fertilizer, sowing, crop problems or storage?"
        )
    return None


def local_answer(message, *, history=None, farm_context=None, language="bn"):
    """Return a local reference answer with narrowly scoped follow-up context."""
    lang = language_code(language)
    text, bn = _text(message), lang == "bn"
    bare = _bare(text)
    if bare in _RESET:
        return _reply("নতুন করে শুরু করি। ফসলের নাম ও আপনার প্রশ্ন লিখুন।" if bn else "Let's start again. Tell me the crop and your question.", "reset", lang, sources=False)
    if bare in _THANKS:
        return _reply("স্বাগতম! অন্য প্রশ্ন থাকলে ফসলের নাম ও কী জানতে চান লিখুন।" if bn else "You're welcome! For another question, tell me the crop and what you need.", "thanks", lang, sources=False)
    if _any(text, _IDENTITY):
        return _reply("আমি AgriTwin-এর স্থানীয় কৃষি সহায়ক। অ্যাপের সংরক্ষিত কৃষি তথ্য দিয়ে উত্তর দিই; কোনো অনলাইন AI বা API ব্যবহার করি না। সেচ, মাটি, সার, রোগ-পোকা, বপন ও ফসল পরিচর্যা নিয়ে প্রশ্ন করতে পারেন।" if bn else "I'm AgriTwin's local farming assistant. I answer from the app's bundled agricultural information without an online AI service or API. Ask about irrigation, soil, fertilizer, crop problems, sowing or crop care.", "identity", lang, sources=False)
    converted = _conversion(text, lang)
    if converted:
        return converted
    topic, crop = _topic(text), _crop(text)
    if topic in {"greeting", "help"} or not text:
        greeting = "স্বাগতম! আমি স্থানীয় কৃষি সহায়ক।" if bn else "Hello! I'm your local farming assistant."
        menu = (
            "সেচ, মাটি পরীক্ষা, সার, বপন, রোগ-পোকা ও সংরক্ষণ নিয়ে সাহায্য করতে পারি। যেমন:\n• ধানের সেচ কীভাবে দেব?\n• টমেটোর পাতায় দাগ—কী দেখব?\n• আলু লাগানোর আগে কী তথ্য লাগবে?\nফসলের নাম ও আপনার প্রশ্ন লিখুন।"
            if bn else "I can help with irrigation, soil tests, fertilizer, sowing, crop problems and storage. For example:\n• How should I water rice?\n• Tomato leaves have spots—what should I check?\n• What should I know before planting potatoes?\nTell me the crop and your question."
        )
        return _reply(greeting + "\n\n" + menu, topic or "help", lang, sources=False)
    prior = _recent_state(history)
    followup = bool(prior["topic"]) and ((topic is None and _short_followup(text)) or _topic_followup(text, topic))
    district, stage = _district(text), _stage(text, lang)
    if followup:
        topic = topic or prior["topic"]
        previous_crop = prior["crop"]
        crop = crop or previous_crop
        district = district or prior["district"]
        if not stage and crop == previous_crop and prior["stage"]:
            stage = _stage(prior["stage"], lang)
    if not topic and crop:
        topic = "care"
    if not topic and _any(text, _CARE) and _farm_crop(farm_context):
        topic = "care"
    if topic in {"irrigation", "soil", "fertilizer", "disease", "pests", "sowing", "care", "storage", "rotation", "drainage"}:
        crop = crop or _farm_crop(farm_context)
    if not topic:
        fallback = (
            "এই প্রশ্নের নির্দিষ্ট উত্তর আমার স্থানীয় কৃষি তথ্যভাণ্ডারে নেই। সেচ, মাটি পরীক্ষা, সার, বপন, রোগ-পোকা বা সংরক্ষণ নিয়ে প্রশ্ন লিখুন।\nযেমন: ‘টমেটোর পাতায় দাগ—কী দেখব?’ ফসলের নাম, বয়স ও সমস্যাটি জানালে পরের ধাপে সাহায্য করতে পারব।"
            if bn else "I don't have a specific answer to that in my local farming library. Ask about irrigation, soil tests, fertilizer, sowing, crop problems or storage.\nFor example: 'Tomato leaves have spots—what should I check?' Tell me the crop, age and issue so I can help with the next step."
        )
        return _reply(fallback, "fallback", lang)
    if topic == "care" and not crop:
        return _reply("কোন ফসলের পরিচর্যা জানতে চান—ধান, আলু, টমেটো, গম, ভুট্টা, পাট নাকি ডাল?" if bn else "Which crop would you like help with—rice, potato, tomato, wheat, maize, jute or pulses?", "care", lang, sources=False)
    body = _checklist(topic, crop, lang)
    source_topic = "sowing" if topic == "care" else topic
    if topic == "weather" and _any(text, ("where", "warning", "advisory", "কোথা", "সতর্ক", "পূর্বাভাস পাব")):
        body = (
            "সর্বশেষ সরকারি আবহাওয়া সতর্কতার জন্য বাংলাদেশ আবহাওয়া অধিদপ্তরের কৃষি আবহাওয়ার পাতাটি দেখুন। নিচের সূত্রের লিংক দিয়ে খুলতে পারেন।\n• আপনার জেলা বা এলাকার জন্য প্রযোজ্য কি না দেখুন।\n• প্রকাশের তারিখ, সতর্কতার সময়সীমা ও উল্লেখ করা ঝুঁকি মিলিয়ে নিন।\n• মাঠের কাজের আগে স্থানীয় কৃষি অফিসের পরামর্শও নিন।\nএই স্থানীয় চ্যাট নিজে নতুন সতর্কতা ডাউনলোড করে না; লিংক খুলতে ইন্টারনেট লাগবে।"
            if bn else "For the latest official weather warnings, open the Bangladesh Meteorological Department's agricultural weather page using the reference link below.\n• Check whether it applies to your district or area.\n• Check its publication date, validity period and stated hazards.\n• Confirm local agricultural advice before planning field work.\nThis local chat does not download new warnings; opening the source requires internet access."
        )
    if body is None:
        try:
            body = get_entry(topic)["answer"][lang]
        except StopIteration:
            body, source_topic = get_entry("fallback")["answer"][lang], "fallback"
    details = []
    if crop:
        details.append(("ফসল" if bn else "Crop") + ": " + CROPS[crop][lang])
    if district:
        details.append(("জেলা" if bn else "District") + ": " + district[lang])
    if stage:
        details.append(("আপনার বলা বয়স বা পর্যায়" if bn else "Age or stage you reported") + ": " + stage)
    if details:
        body = " · ".join(details) + "\n\n" + body
    if topic in {"disease", "pests", "irrigation", "fertilizer", "sowing", "care"}:
        if crop:
            question = _care_question(crop, lang)
        else:
            question = "কোন ফসল ও বয়স? জেলা এবং নির্দিষ্ট সমস্যাটি লিখুন।" if bn else "Which crop and age? Tell me the district and the specific issue."
        if stage and district and crop:
            question = "এখন কোন লক্ষণ বা মাঠের অবস্থা দেখছেন? কী কাজ করতে চান?" if bn else "What symptoms or field conditions do you see now, and what operation are you planning?"
        body += "\n\n" + question
    return _reply(body, topic, lang, sources=False) | {"sources": _reply("", source_topic, lang)["sources"]}
