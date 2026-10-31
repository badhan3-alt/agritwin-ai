"""Local farmer conversation and opt-in saved NASA context.

All chat answers are generated from bundled information inside Django.
No external model, API key, network request, or model download is used.
"""
import math
import re
from urllib.parse import urlsplit

from .knowledge import contains, knowledge_answer, language_code, normalize
from .local import local_answer


MAX_MESSAGE_CHARS = 2000


MAX_HISTORY_MESSAGES = 8


MAX_HISTORY_CHARS = 8000


MAX_ANSWER_CHARS = 12000


NASA_DOCS_URL = "https://power.larc.nasa.gov/docs/services/api/temporal/climatology/"


_NUMBER_TRANSLATION = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


_CLIMATE_FIELDS = (
    "total_precip_mm", "rabi_dry_season_precip_mm", "avg_annual_temp_c",
    "heat_stress_months", "rabi_soil_wetness_avg", "dry_season_severity",
    "water_stress_index", "kharif_precip_mm", "kharif1_precip_mm", "kharif2_precip_mm",
)


def _clean_text(value, limit):
    if not isinstance(value, str):
        return ""
    # Retain Bangla joiners, Unicode letters and normal newlines.
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value).strip()[:limit]


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return value if math.isfinite(value) else None


def _display(value, lang):
    value = str(value)
    if lang != "bn":
        return value
    # The period is source metadata, not a newly calculated date range.
    months = {
        "January": "জানুয়ারি", "February": "ফেব্রুয়ারি", "March": "মার্চ",
        "April": "এপ্রিল", "May": "মে", "June": "জুন", "July": "জুলাই",
        "August": "আগস্ট", "September": "সেপ্টেম্বর", "October": "অক্টোবর",
        "November": "নভেম্বর", "December": "ডিসেম্বর",
    }
    for english, bangla in months.items():
        value = value.replace(english, bangla)
    return value.translate(_NUMBER_TRANSLATION)


def _is_nasa_source(url):
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https" and parsed.netloc == "power.larc.nasa.gov"
            and parsed.path.rstrip("/") in {
                "/api/temporal/climatology/point", "/docs/services/api/temporal/climatology",
            }
        )
    except (TypeError, ValueError, AttributeError):
        return False


def _safe_context(context):
    """Defense in depth: exclude IDs, coordinates, arbitrary keys and raw data."""
    if not isinstance(context, dict):
        return None
    farm = context.get("farm")
    safe_farm = {}
    if isinstance(farm, dict):
        for key in ("location_name", "soil_type", "irrigation", "priority"):
            value = _clean_text(farm.get(key), 160)
            if value:
                safe_farm[key] = value
        for key in ("soil_ph", "area"):
            value = _number(farm.get(key))
            if value is not None:
                safe_farm[key] = value
        crops = farm.get("crops")
        if isinstance(crops, (list, tuple)):
            safe_farm["crops"] = [
                value for crop in crops[:12] if (value := _clean_text(crop, 80))
            ]

    safe_climate = None
    climate = context.get("climate")
    if isinstance(climate, dict) and climate.get("status") == "live":
        provenance = climate.get("provenance")
        summary = climate.get("annual_summary")
        if (
            isinstance(provenance, dict) and isinstance(summary, dict)
            and _is_nasa_source(provenance.get("url"))
            and _clean_text(provenance.get("period"), 120)
            and _clean_text(provenance.get("retrieved_at"), 80)
        ):
            clean_summary = {
                key: value for key in _CLIMATE_FIELDS
                if (value := _number(summary.get(key))) is not None
            }
            if clean_summary:
                safe_climate = {
                    "status": "live", "annual_summary": clean_summary,
                    "provenance": {
                        "period": _clean_text(provenance["period"], 120),
                        "retrieved_at": _clean_text(provenance["retrieved_at"], 80),
                        # Query strings can contain exact coordinates. The
                        # public docs identify the source without exposing exact coordinates.
                        "url": NASA_DOCS_URL,
                    },
                }

    safe_strategies = []
    strategies = context.get("strategies")
    if safe_climate and isinstance(strategies, (list, tuple)):
        for item in strategies[:6]:
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name"), 160)
            score = _number(item.get("composite_score"))
            if name and score is not None and isinstance(item.get("is_eligible"), bool):
                safe_strategies.append({
                    "name": name, "composite_score": score,
                    "is_eligible": item["is_eligible"],
                })
    if not safe_farm and not safe_climate:
        return None
    return {"farm": safe_farm, "climate": safe_climate, "strategies": safe_strategies}


def _safe_history(history):
    if not isinstance(history, (list, tuple)):
        return []
    result, remaining = [], MAX_HISTORY_CHARS
    # Keep the latest valid user/assistant turns; never accept injected roles.
    for item in reversed(history[-MAX_HISTORY_MESSAGES * 3:]):
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content", item.get("body"))
        text = _clean_text(content, min(MAX_MESSAGE_CHARS, remaining))
        if not text:
            continue
        result.append({"role": item["role"], "content": text})
        remaining -= len(text)
        if len(result) >= MAX_HISTORY_MESSAGES or remaining <= 0:
            break
    return list(reversed(result))


def _context_question(message):
    """Recognize requests for saved farm data and historical NASA climate."""
    text = normalize(message)
    if any(contains(text, word) for word in (
        "nasa", "নাসা", "স্যাটেলাইট", "satellite", "climatology",
        "climate data", "জলবায়ু তথ্য", "জলবায়ু তথ্য",
    )):
        return True
    profile_phrases = (
        "আমার খামারের তথ্য", "আমার জমির তথ্য", "আমার খামারের বিশ্লেষণ",
        "আমার মাটির পিএইচ", "আমার মাটির ph", "আমার জমির ph",
        "আমার খামারের জলবায়ু", "আমার খামারের জলবায়ু",
        "my farm data", "my farm summary", "my farm analysis", "my soil ph",
        "my farm climate", "my farm's climate", "my farm's data",
    )
    return any(contains(text, word) for word in profile_phrases)


def _context_answer(message, context, lang):
    if not context:
        return knowledge_answer(message, lang, topic="nasa")
    bn = lang == "bn"
    farm, climate = context["farm"], context["climate"]
    lines = []
    if farm:
        lines.append("আপনার যুক্ত করা খামারের তথ্য:" if bn else "Your attached farm summary:")
        labels = {
            "location_name": ("এলাকা", "Area"), "soil_type": ("মাটির ধরন", "Soil type"),
            "irrigation": ("সেচের ব্যবস্থা", "Irrigation"), "priority": ("অগ্রাধিকার", "Priority"),
        }
        for key, labels_for_key in labels.items():
            if farm.get(key):
                lines.append(f"• {labels_for_key[0 if bn else 1]}: {_display(farm[key], lang)}")
        if farm.get("crops"):
            label = "ফসল" if bn else "Crops"
            lines.append(f"• {label}: {', '.join(_display(crop, lang) for crop in farm['crops'])}")
        if farm.get("area") is not None:
            label, unit = ("জমির আয়তন", "একর") if bn else ("Farm size", "acres")
            lines.append(f"• {label}: {_display(farm['area'], lang)} {unit}")
        if farm.get("soil_ph") is not None:
            label = "আপনার দেওয়া মাটির pH" if bn else "Soil pH entered by you"
            lines.append(f"• {label}: {_display(farm['soil_ph'], lang)}")
        else:
            lines.append("মাটির pH-এর পরীক্ষার ফল দেওয়া নেই।" if bn else "No soil pH test result was provided.")

    if climate:
        period = _display(climate["provenance"]["period"], lang)
        lines.append(
            f"\nসংরক্ষিত নাসা POWER জলবায়ু গড়ের সময়কাল: {period}।"
            if bn else f"\nStored NASA POWER climatology period: {period}."
        )
        summary = climate["annual_summary"]
        values = (
            ("total_precip_mm", "বার্ষিক মোট বৃষ্টির দীর্ঘমেয়াদি গড়", "Long-term mean annual precipitation", "মিমি", "mm"),
            ("rabi_dry_season_precip_mm", "রবি শুষ্ক মৌসুমের বৃষ্টির দীর্ঘমেয়াদি গড়", "Long-term mean Rabi dry-season precipitation", "মিমি", "mm"),
            ("avg_annual_temp_c", "বার্ষিক গড় তাপমাত্রার দীর্ঘমেয়াদি গড়", "Long-term mean annual temperature", "°সে", "°C"),
        )
        for key, label_bn, label_en, unit_bn, unit_en in values:
            if key in summary:
                lines.append(f"• {label_bn if bn else label_en}: {_display(summary[key], lang)} {unit_bn if bn else unit_en}")
        if context["strategies"] and any(contains(message, word) for word in (
            "rotation", "strategy", "score", "recommend", "বিন্যাস", "স্কোর", "সুপারিশ", "কৌশল",
        )):
            eligible = [item for item in context["strategies"] if item["is_eligible"]]
            if eligible:
                top = max(eligible, key=lambda item: item["composite_score"])
                score = _display(top["composite_score"], lang)
                lines.append(
                    f"সংরক্ষিত তুলনায় সর্বোচ্চ উপযুক্ত স্কোর: {top['name']} — {score}। এটি পরিকল্পনার স্কোর, ফলন বা লাভের নিশ্চয়তা নয়।"
                    if bn else f"Highest eligible score in the stored comparison: {top['name']} — {score}. This is a planning score, not a yield or profit guarantee."
                )
            else:
                lines.append("সংরক্ষিত তুলনায় কোনো বিন্যাসকে উপযুক্ত পাওয়া যায়নি।" if bn else "No rotation is marked eligible in the stored comparison.")
        lines.append(
            "এগুলো আঞ্চলিক দীর্ঘমেয়াদি গড়; আজকের আবহাওয়া, ভবিষ্যৎ বৃষ্টির পূর্বাভাস বা জমির সরাসরি পরিমাপ নয়। নাসা-এর এই তথ্য দিয়ে মাটির pH বা নাইট্রোজেন-ফসফরাস-পটাশ মাপা যায় না।"
            if bn else "These are regional historical averages, not current weather, future rainfall forecasts or direct field measurements. This NASA data cannot measure field pH or nitrogen, phosphorus and potassium."
        )
    else:
        lines.append(
            "এই খামারের যাচাই করা নাসা জলবায়ু তথ্য এখন যুক্ত নেই। খামারের বিশ্লেষণ সম্পন্ন করে আবার তথ্য যুক্ত করুন। কোনো বৃষ্টি বা তাপমাত্রার মান অনুমান করছি না।"
            if bn else "No verified NASA climate summary is attached for this farm. Complete the farm analysis and attach the context again. No rainfall or temperature values have been assumed."
        )
    source = knowledge_answer("", lang, topic="nasa")["sources"]
    return {"text": "\n".join(lines), "mode": "knowledge", "sources": source, "topic": "nasa"}


def answer_question(message, *, history=None, farm_context=None, language="bn"):
    """Answer locally using bounded conversation and explicitly shared farm data."""
    lang = language_code(language)
    message = _clean_text(message, MAX_MESSAGE_CHARS)
    context = _safe_context(farm_context)
    if _context_question(message):
        answer = _context_answer(message, context, lang)
        answer["mode"] = "local"
        return answer
    answer = local_answer(
        message, history=_safe_history(history), farm_context=context, language=lang,
    )
    answer["mode"] = "local"
    answer["text"] = _clean_text(answer["text"], MAX_ANSWER_CHARS)
    return answer
