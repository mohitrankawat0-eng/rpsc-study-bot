"""
planning.py - Adaptive daily study plan generation.
Uses dynamic priority formula:
  topic_priority = (1 - accuracy) * pyq_weight * completion_pressure * streak_multiplier
65% Paper-II focus by default; adjusts based on diagnostic profile.
"""
import random
import math
from datetime import date
from db import (
    get_all_topics, save_daily_plan, get_today_plan,
    get_user_profile, get_streak, get_user
)
from config import DAILY_BLOCKS, TIMEZONE
from datetime import datetime, date, timedelta
import pytz


SECTION_EMOJIS = {
    "SrSec":    "🔬",
    "Grad":     "🧬",
    "Pedagogy": "📖",
    "ICT":      "💻",
    "History":  "🏛️",
    "Geography":"🗺️",
    "Polity":   "⚖️",
    "MCQ":      "✅",
    "Review":   "📝",
}


async def _compute_topic_priority(
        topic: dict,
        topic_accuracy: dict,
        streak: int,
        completion_ratio: float,
) -> float:
    """
    Dynamic priority score for a topic.
    Higher = should be studied more urgently.
    """
    section   = topic['section']
    pyq_w     = topic.get('pyq_weight', 1) or 1
    marks_w   = topic.get('marks_weight', 1) or 1

    # Accuracy penalty: low accuracy → higher priority
    acc  = topic_accuracy.get(section, 0.5)   # default 50% if unknown
    acc  = max(0.01, min(1.0, acc))

    # Completion pressure: lower progress → higher urgency
    pressure = max(0.1, 1.0 - completion_ratio)

    # Streak multiplier: longer streak → slight chill, shorter → urgency
    streak_mult = 1.0 + (0.1 * max(0, 5 - streak))   # up to 1.5 for streak=0

    priority_score = (1.0 - acc) * pyq_w * pressure * streak_mult * marks_w
    return round(priority_score, 3)


    # Build timeline starting from the Wake-up time and inserts breaks for Lunch, Dinner, and Snacks.
    profile = await get_user_profile(user_id)
    streak  = await get_streak(user_id)

    topic_accuracy    = profile.get('topic_accuracy', {}) if profile else {}
    daily_hours       = profile.get('recommended_daily_hours', 10.5) if profile else 10.5
    error_type        = profile.get('error_type', 'conceptual') if profile else 'conceptual'

    wake_up = profile.get('wake_up_time', '06:00') if profile else '06:00'
    lunch   = profile.get('lunch_time', '13:00')   if profile else '13:00'
    dinner  = profile.get('dinner_time', '20:30')  if profile else '20:30'
    snack   = profile.get('snack_time', '17:00')   if profile else '17:00'

    # Check for Rest Day (every 14 days)
    user_data = await get_user(user_id)
    if user_data:
        try:
            # created_at is usually like '2026-02-22' or '2026-02-22 06:30:34'
            created_str = user_data['created_at'].split()[0]
            created = datetime.strptime(created_str, "%Y-%m-%d")
            days_since = (datetime.now() - created).days
            if days_since > 0 and days_since % 14 == 0:
                return await _generate_rest_day_plan(user_id)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Rest day check error: {e}")

    topics_p2 = await get_all_topics(paper=2)
    topics_p1 = await get_all_topics(paper=1)

    # Add dynamic priority to each topic
    for t in topics_p2 + topics_p1:
        comp_ratio = topic_accuracy.get(t['section'], 0.5)
        t['_dyn_priority'] = await _compute_topic_priority(
            t, topic_accuracy, streak, comp_ratio
        )

    def adaptive_pick(pool: list) -> dict | None:
        if not pool:
            return None
        weights = [max(0.01, t.get('_dyn_priority', 1.0)) for t in pool]
        return random.choices(pool, weights=weights, k=1)[0]

    # Scale block hours proportionally to recommended daily hours
    hour_scale = daily_hours / 10.5

    # Build timeline
    current_time_dt = datetime.combine(date.today(), datetime.strptime(wake_up, "%H:%M").time())
    
    blocks = []
    for block_def in DAILY_BLOCKS:
        section = block_def['section']
        paper   = block_def['paper']
        adj_hrs = round(block_def['hours'] * hour_scale, 1)
        
        # Check for breaks
        lunch_dt  = datetime.combine(date.today(), datetime.strptime(lunch, "%H:%M").time())
        snack_dt  = datetime.combine(date.today(), datetime.strptime(snack, "%H:%M").time())
        dinner_dt = datetime.combine(date.today(), datetime.strptime(dinner, "%H:%M").time())

        # If block overlaps with lunch, move it after lunch
        if current_time_dt < lunch_dt and (current_time_dt + timedelta(hours=adj_hrs)) > lunch_dt:
            current_time_dt = lunch_dt + timedelta(minutes=45) # 45 min break
        
        # If block overlaps with snack, move it
        if current_time_dt < snack_dt and (current_time_dt + timedelta(hours=adj_hrs)) > snack_dt:
            current_time_dt = snack_dt + timedelta(minutes=20) # 20 min break

        # If block overlaps with dinner, move it
        if current_time_dt < dinner_dt and (current_time_dt + timedelta(hours=adj_hrs)) > dinner_dt:
            current_time_dt = dinner_dt + timedelta(minutes=45) # 45 min break

        start_time_str = current_time_dt.strftime("%I:%M %p")

        if paper == 2:
            sec_pool = [t for t in topics_p2 if t['section'] == section] or topics_p2
            topic    = adaptive_pick(sec_pool)
        elif paper == 1:
            topic = adaptive_pick(topics_p1)
        else:
            topic = None

        method_hint = ""
        if topic and error_type == "conceptual":
            method_hint = " [Theory→MCQ]"
        elif topic:
            method_hint = " [MCQ→Review]"

        block = {
            "label":             f"{start_time_str}: {block_def['label']}{method_hint}",
            "section":           section,
            "paper":             paper,
            "hours":             adj_hrs,
            "emoji":             block_def['emoji'],
            "topic_id":          topic['topic_id']         if topic else None,
            "topic_name":        topic['name']              if topic else "–",
            "free_pdf_link":     topic['free_pdf_link']     if topic else "",
            "recommended_books": topic['recommended_books'] if topic else "",
            "marks_weight":      topic['marks_weight']      if topic else 0,
            "dyn_priority":      topic.get('_dyn_priority', 0) if topic else 0,
        }
        blocks.append(block)
        current_time_dt += timedelta(hours=adj_hrs)

    await save_daily_plan(user_id, blocks)
    return blocks


async def _generate_rest_day_plan(user_id: int) -> list[dict]:
    """Light plan for the fortnightly rest day."""
    blocks = [
        {
            "label": "10:00 AM: Relax & Recharge 🧘",
            "section": "Review",
            "paper": 0,
            "hours": 0.5,
            "emoji": "☀️",
            "status": "pending",
            "topic_name": "No heavy study today. Chill out!"
        },
        {
            "label": "06:00 PM: Weekly Light Review",
            "section": "Review",
            "paper": 0,
            "hours": 1.0,
            "emoji": "📝",
            "status": "pending",
            "topic_name": "Just flip through your notes."
        }
    ]
    await save_daily_plan(user_id, blocks)
    return blocks


async def format_plan_message(blocks: list[dict], daily_hours: float = 10.5) -> str:
    today_str = date.today().strftime("%A, %d %B %Y")
    lines = [
        f"📅 *Study Plan — {today_str}*",
        f"⏱️ Total: *{daily_hours}h* | 📊 65% Paper-II | Adaptive Priority\n"
    ]

    for i, b in enumerate(blocks, 1):
        status_icon = {"done": "✅", "skipped": "⏭️", "pending": "⏳"}.get(
            b.get('status', 'pending'), "⏳"
        )
        emoji = SECTION_EMOJIS.get(b['section'], b.get('emoji', '📌'))
        lines.append(f"*Block {i}* {status_icon} {emoji} `{b['label']}`")
        lines.append(f"  ⏱️ {b['hours']}h | 🎯 {b.get('marks_weight', '')} marks")

        if b.get('topic_name') and b['topic_name'] != '–':
            pri_arrow = "🔺" if b.get('dyn_priority', 0) > 5 else ""
            lines.append(f"  📚 *{b['topic_name']}* {pri_arrow}")

        if b.get('recommended_books'):
            lines.append(f"  📖 {b['recommended_books']}")

        if b.get('free_pdf_link'):
            lines.append(f"  🔗 [Open Free PDF]({b['free_pdf_link']})")

        lines.append("")

    lines.append(f"🔥 *Stay focused! {daily_hours}h of disciplined study = RPSC Selection!*")
    return "\n".join(lines)


async def get_next_pending_block(user_id: int) -> dict | None:
    blocks = await get_today_plan(user_id)
    for b in blocks:
        if b.get('status') == 'pending':
            return b
    return None


async def format_block_message(block: dict, block_num: int) -> str:
    emoji = SECTION_EMOJIS.get(block.get('section', ''), "📌")
    lines = [
        f"🚀 *Next Block — #{block_num}*",
        f"{emoji} *{block.get('label', 'Study Block')}*",
        f"",
        f"⏱️ Duration: *{block.get('hours', 1)}h*",
    ]
    if block.get('topic_name') and block['topic_name'] != '–':
        lines.append(f"📚 Topic: *{block['topic_name']}*")
    if block.get('marks_weight'):
        lines.append(f"🎯 Marks Weight: *{block['marks_weight']}*")
    if block.get('recommended_books'):
        lines.append(f"📖 Book: {block['recommended_books']}")
    if block.get('free_pdf_link'):
        lines.append(f"🔗 [Open NCERT PDF]({block['free_pdf_link']})")
    lines += [
        "",
        "💪 *Start now. Every minute counts for RPSC!*",
        "Use `/done <minutes> <score>` when finished."
    ]
    return "\n".join(lines)


async def get_exam_countdown() -> str:
    exam_date = date(2025, 12, 1)
    today     = date.today()
    delta     = exam_date - today
    if delta.days < 0:
        return "🎓 Exam date has passed. Review your performance!"
    weeks, days = divmod(delta.days, 7)
    return f"🗓️ *Exam Countdown:* {delta.days} days ({weeks}w {days}d) remaining!"


async def format_profile_message(user_id: int) -> str:
    """Format the /profile snapshot."""
    from db import compute_weak_topics, get_calibration_history
    profile  = await get_user_profile(user_id)
    streak   = await get_streak(user_id)
    weak     = await compute_weak_topics(user_id)
    cal_hist = await get_calibration_history(user_id, days=3)

    if not profile:
        return "❌ No profile found. Complete the diagnostic test first with /start"

    ta = profile.get('topic_accuracy', {})

    section_lines = []
    for sec, acc in ta.items():
        emoji = "✅" if acc >= 0.6 else "⚠️" if acc >= 0.4 else "🔴"
        section_lines.append(f"  {emoji} {sec}: *{int(acc*100)}%*")

    cal_lines = []
    for c in cal_hist:
        cal_lines.append(
            f"  {c['cal_date']}: acc={int(c['accuracy']*100)}% "
            f"| done={int(c['completion_rate']*100)}% "
            f"| {c['actual_hours']}h"
        )

    return (
        f"👤 *Your Capability Snapshot*\n\n"
        f"📊 *Baseline Scores*\n"
        f"  🏛️ Paper I:  *{int(profile['baseline_paper1_score']*100)}%*\n"
        f"  🔬 Paper II: *{int(profile['baseline_paper2_score']*100)}%*\n\n"
        f"🧠 *Learning Profile*\n"
        f"  ⏱️ Avg response: *{profile['avg_response_time']}s/Q*\n"
        f"  📖 Style: *{profile['learning_style']}*\n"
        f"  ❌ Error type: *{profile['error_type']}*\n"
        f"  📉 Skip rate: *{int(profile['skip_rate']*100)}%*\n\n"
        f"📅 *Adaptive Settings*\n"
        f"  ⏱️ Daily goal: *{profile['recommended_daily_hours']}h*\n"
        f"  ⏲️ Block length: *{profile['recommended_block_len']} min*\n"
        f"  🔥 Streak: *{streak} days*\n\n"
        f"🎯 *Topic Accuracy*\n"
        + ("\n".join(section_lines) if section_lines else "  _No data yet_") + "\n\n"
        f"🔴 *Weak Topics:* {len(weak)}\n"
        + (", ".join(w['name'] for w in weak[:3]) if weak else "_None — great work!_") + "\n\n"
        f"📈 *Last 3 Calibrations*\n"
        + ("\n".join(cal_lines) if cal_lines else "  _No calibrations yet_") + "\n\n"
        f"_Use `/calibrate` for a fresh 5Q re-assessment._"
    )
