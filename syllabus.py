"""
syllabus.py - Syllabus display and book recommendations
"""
from db import get_all_topics, get_topic


SECTION_EMOJIS = {
    "SrSec":    "🔬",
    "Grad":     "🧬",
    "Pedagogy": "📖",
    "ICT":      "💻",
    "History":  "🏛️",
    "Geography":"🗺️",
    "Polity":   "⚖️",
}

PRIORITY_EMOJI = {
    "HIGH":   "🔴",
    "MEDIUM": "🟡",
    "LOW":    "🟢",
}


async def get_syllabus_summary(paper: int | None = None) -> str:
    topics = await get_all_topics(paper)
    if not topics:
        return "❌ No syllabus data found."

    # Group by section
    sections: dict[str, list] = {}
    for t in topics:
        sec = t['section']
        sections.setdefault(sec, []).append(t)

    lines = []
    if paper == 2:
        lines.append("📚 *PAPER II — Biology Syllabus*\n")
    elif paper == 1:
        lines.append("📚 *PAPER I — General Knowledge Syllabus*\n")
    else:
        lines.append("📚 *Complete RPSC Syllabus*\n")

    for section, topics_in_sec in sections.items():
        emoji = SECTION_EMOJIS.get(section, "📌")
        total_marks = sum(t['marks_weight'] for t in topics_in_sec)
        lines.append(f"\n{emoji} *{section}* _(~{total_marks} marks)_")
        for t in topics_in_sec:
            pri  = PRIORITY_EMOJI.get(t['priority'], "⚪")
            line = (
                f"  {pri} *{t['name']}*\n"
                f"     📊 {t['marks_weight']} marks | ⏱️ Target: {t['target_hours']}h\n"
                f"     📖 {t['recommended_books']}\n"
                f"     🔗 [Free PDF]({t['free_pdf_link']})"
            )
            lines.append(line)

    return "\n".join(lines)


async def get_topic_detail(topic_id: int) -> str:
    t = await get_topic(topic_id)
    if not t:
        return "❌ Topic not found."

    emoji = SECTION_EMOJIS.get(t['section'], "📌")
    pri   = PRIORITY_EMOJI.get(t['priority'], "⚪")

    text = (
        f"{emoji} *{t['name']}*\n\n"
        f"{pri} Priority: *{t['priority']}*\n"
        f"📊 Marks Weight: *{t['marks_weight']}*\n"
        f"📅 PYQ Weight: *{t.get('pyq_weight', 'N/A')}*\n"
        f"⏱️ Target Hours: *{t['target_hours']}h*\n"
        f"📝 Section: *{t['section']}*\n\n"
        f"📖 *Recommended Books:*\n{t['recommended_books']}\n\n"
        f"🔗 *Free PDF:* [Click Here]({t['free_pdf_link']})"
    )
    return text


async def get_books_list() -> str:
    topics = await get_all_topics()
    seen = set()
    lines = ["📚 *Recommended Books & FREE PDFs*\n"]
    for t in sorted(topics, key=lambda x: (x['paper'], x['section'])):
        key = t['free_pdf_link']
        if key in seen:
            continue
        seen.add(key)
        emoji = SECTION_EMOJIS.get(t['section'], "📌")
        lines.append(
            f"{emoji} *{t['name']}*\n"
            f"   📖 {t['recommended_books']}\n"
            f"   🔗 [Download FREE PDF]({t['free_pdf_link']})"
        )
    return "\n\n".join(lines)
