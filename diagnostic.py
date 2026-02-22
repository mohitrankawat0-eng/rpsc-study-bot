"""
diagnostic.py - 30-Question Adaptive Diagnostic Test Engine
Runs BEFORE any schedule on /start for new users.
Flow: Q1 → inline A/B/C/D → 90s auto-skip timer → Q2 → ... → Analysis
"""
import asyncio
import time
import json
from datetime import datetime

from aiogram import Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from db import (
    get_diagnostic_questions, save_diagnostic_results,
    mark_user_onboarded, update_topic_accuracy
)

# ── In-memory diagnostic state ───────────────────────────────────────────────
_active_diagnostics: dict[int, dict] = {}   # user_id → state

QUESTION_TIMEOUT_SEC = 90   # auto-skip after this many seconds

SECTION_LABELS = {
    "History":      "📜 Rajasthan History",
    "Geography":    "🗺️ Rajasthan Geography",
    "Polity":       "⚖️ Rajasthan Polity",
    "SrSec":        "🔬 Biology (Sr. Secondary)",
    "Grad":         "🧬 Biology (Graduate)",
    "Pedagogy":     "📖 Pedagogy",
    "ICT":          "💻 ICT",
    "MentalAbility":"🧠 Mental Ability",
}


def _diag_keyboard(q_index: int, opts: list[str]) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D"]
    buttons = []
    for i, opt in enumerate(opts):
        if opt:
            buttons.append([InlineKeyboardButton(
                text=f"{labels[i]}) {opt}",
                callback_data=f"diag:{q_index}:{i}"
            )])
    buttons.append([InlineKeyboardButton(
        text="⏭️ Skip this question",
        callback_data=f"diag:{q_index}:skip"
    )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def start_diagnostic(user_id: int, bot: Bot, chat_id: int) -> None:
    """Start the 30-question diagnostic test."""
    questions = await get_diagnostic_questions()
    if not questions:
        await bot.send_message(
            chat_id,
            "⚠️ Diagnostic questions not found in DB. "
            "Please run setup.py first.\n"
            "Skipping to standard plan — use /today to begin!"
        )
        await mark_user_onboarded(user_id)
        return

    _active_diagnostics[user_id] = {
        "chat_id":    chat_id,
        "questions":  questions,
        "current":    0,
        "correct":    0,
        "wrong":      0,
        "skipped":    0,
        "start_time": time.time(),
        "q_start":    time.time(),
        "response_times": [],
        "results_by_section": {},   # section → {correct, total}
        "last_msg_id": None,        # for cleanup
        "auto_skip_task": None,
    }

    intro = (
        "🎯 *Welcome! Let's assess your baseline — 30 Questions*\n\n"
        "📋 *Test breakdown:*\n"
        "  🏛️ Paper I (Rajasthan GK): 8 questions\n"
        "  🔬 Paper II (Biology + Pedagogy): 17 questions\n"
        "  🧠 Mental Ability: 5 questions\n\n"
        "⏱️ *90 seconds per question* — unanswered = auto-skip\n"
        "🎯 The bot will personalise your daily plan based on results!\n\n"
        "_Starting in 3 seconds…_"
    )
    await bot.send_message(chat_id, intro, parse_mode="Markdown")
    await asyncio.sleep(3)
    await _send_diagnostic_question(bot, user_id)


async def _send_diagnostic_question(bot: Bot, user_id: int) -> None:
    state = _active_diagnostics.get(user_id)
    if not state:
        return

    # Cancel previous auto-skip task
    if state.get("auto_skip_task") and not state["auto_skip_task"].done():
        state["auto_skip_task"].cancel()

    idx       = state['current']
    questions = state['questions']

    if idx >= len(questions):
        await _finish_diagnostic(bot, user_id)
        return

    q    = questions[idx]
    opts = [q.get('opt_a', ''), q.get('opt_b', ''), q.get('opt_c', ''), q.get('opt_d', '')]
    labels = ["A", "B", "C", "D"]
    opts_text = "\n".join(
        f"  *{labels[i]})* {o}" for i, o in enumerate(opts) if o
    )
    section_label = SECTION_LABELS.get(q.get('section', ''), q.get('section', ''))

    text = (
        f"📝 *Diagnostic Q{idx + 1}/30* — {section_label}\n\n"
        f"*{q['question']}*\n\n"
        f"{opts_text}\n\n"
        f"⏱️ _{QUESTION_TIMEOUT_SEC}s remaining_"
    )

    kb  = _diag_keyboard(idx, opts)
    msg = await bot.send_message(state['chat_id'], text,
                                  parse_mode="Markdown",
                                  reply_markup=kb)
    state['last_msg_id'] = msg.message_id
    state['q_start']     = time.time()

    # Schedule auto-skip
    task = asyncio.create_task(
        _auto_skip_after_timeout(bot, user_id, idx)
    )
    state['auto_skip_task'] = task


async def _auto_skip_after_timeout(bot: Bot, user_id: int, q_index: int) -> None:
    await asyncio.sleep(QUESTION_TIMEOUT_SEC)
    state = _active_diagnostics.get(user_id)
    if not state or state['current'] != q_index:
        return  # Already answered
    state['skipped'] += 1
    state['current'] += 1
    try:
        await bot.edit_message_reply_markup(
            chat_id    = state['chat_id'],
            message_id = state['last_msg_id'],
            reply_markup = None
        )
    except Exception:
        pass
    await bot.send_message(
        state['chat_id'],
        f"⏰ *Q{q_index + 1} auto-skipped* (time limit reached)",
        parse_mode="Markdown"
    )
    await _send_diagnostic_question(bot, user_id)


async def handle_diagnostic_answer(callback: CallbackQuery, bot: Bot) -> None:
    """Handle inline button callbacks from diagnostic questions."""
    data   = callback.data  # diag:<q_index>:<answer>
    parts  = data.split(":")
    if len(parts) < 3:
        return

    q_index_str = parts[1]
    answer_str  = parts[2]
    user_id     = callback.from_user.id
    state       = _active_diagnostics.get(user_id)

    if not state:
        await callback.answer("No active diagnostic.", show_alert=True)
        return

    q_index = int(q_index_str)
    if state['current'] != q_index:
        await callback.answer("Already answered!", show_alert=True)
        return

    # Cancel auto-skip
    if state.get("auto_skip_task") and not state["auto_skip_task"].done():
        state["auto_skip_task"].cancel()

    response_time = time.time() - state['q_start']
    state['response_times'].append(response_time)

    q    = state['questions'][q_index]
    opts = [q.get('opt_a', ''), q.get('opt_b', ''), q.get('opt_c', ''), q.get('opt_d', '')]
    sec  = q.get('section', 'Unknown')

    # Track by section
    if sec not in state['results_by_section']:
        state['results_by_section'][sec] = {'correct': 0, 'total': 0}
    state['results_by_section'][sec]['total'] += 1

    # Remove keyboard
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if answer_str == "skip":
        state['skipped'] += 1
        feedback = f"⏭️ Skipped Q{q_index + 1}"
    else:
        chosen      = int(answer_str)
        correct_idx = q['answer_idx']
        labels      = ["A", "B", "C", "D"]
        if chosen == correct_idx:
            state['correct'] += 1
            state['results_by_section'][sec]['correct'] += 1
            feedback = f"✅ Q{q_index + 1}: Correct!"
        else:
            state['wrong'] += 1
            feedback = (
                f"❌ Q{q_index + 1}: Wrong\n"
                f"   Correct: *{labels[correct_idx]}) {opts[correct_idx]}*"
            )

    await callback.message.reply(feedback, parse_mode="Markdown")
    await callback.answer()

    state['current'] += 1
    await asyncio.sleep(0.5)
    await _send_diagnostic_question(bot, user_id)


async def _finish_diagnostic(bot: Bot, user_id: int) -> None:
    """Analyse results and save profile."""
    state = _active_diagnostics.pop(user_id, None)
    if not state:
        return

    total    = len(state['questions'])
    correct  = state['correct']
    wrong    = state['wrong']
    skipped  = state['skipped']
    results  = state['results_by_section']

    # Section accuracy
    topic_accuracy = {}
    for sec, data in results.items():
        acc = data['correct'] / data['total'] if data['total'] > 0 else 0
        topic_accuracy[sec] = round(acc, 2)

    # Paper-level scores
    p1_secs  = ['History', 'Geography', 'Polity']
    p2_secs  = ['SrSec', 'Grad', 'Pedagogy', 'ICT']

    def section_score(secs):
        tot = sum(results[s]['total']   for s in secs if s in results)
        cor = sum(results[s]['correct'] for s in secs if s in results)
        return round(cor / tot, 2) if tot > 0 else 0

    p1_score = section_score(p1_secs)
    p2_score = section_score(p2_secs)

    avg_rt   = round(sum(state['response_times']) / len(state['response_times']), 1) \
               if state['response_times'] else 45.0
    skip_rate = round(skipped / total, 2)

    recs = await save_diagnostic_results(
        user_id, p1_score, p2_score, topic_accuracy, avg_rt, skip_rate
    )
    await mark_user_onboarded(user_id)

    # Update per-section accuracy in profile
    for sec, acc in topic_accuracy.items():
        await update_topic_accuracy(user_id, sec, acc)

    # Build analysis message
    def flag(acc: float) -> str:
        return "✅" if acc >= 0.6 else "⚠️" if acc >= 0.4 else "🔴"

    section_lines = []
    for sec, data in results.items():
        acc = data['correct'] / data['total'] if data['total'] > 0 else 0
        lbl = SECTION_LABELS.get(sec, sec)
        section_lines.append(
            f"  {flag(acc)} {lbl}: *{data['correct']}/{data['total']}* "
            f"({int(acc*100)}%)"
        )

    # Weakest section
    weakest = sorted(
        [(s, d['correct']/d['total'] if d['total'] > 0 else 0)
         for s, d in results.items()],
        key=lambda x: x[1]
    )
    weak_sec = SECTION_LABELS.get(weakest[0][0], weakest[0][0]) if weakest else "–"

    speed_label = "Fast" if avg_rt < 30 else "Normal" if avg_rt < 60 else "Careful/Slow"
    determination = "High" if skip_rate < 0.1 else "Medium" if skip_rate < 0.3 else "Low"

    msg = (
        f"🎯 *Diagnostic Complete!*\n\n"
        f"📊 *Baseline Scores*\n"
        f"  📋 Total: *{correct}/{total}* ({int((correct/total)*100)}%)\n"
        f"  🏛️ Paper I: *{int(p1_score*100)}%* "
        f"({'strong' if p1_score > 0.6 else '⚠️ needs work'})\n"
        f"  🔬 Paper II: *{int(p2_score*100)}%* "
        f"({'strong' if p2_score > 0.6 else '⚠️ needs work'})\n\n"
        f"📈 *Section Breakdown*\n"
        + "\n".join(section_lines) + "\n\n"
        f"⚡ *Your Learning Profile*\n"
        f"  ⏱️ Speed: *{avg_rt}s/question* → {speed_label}\n"
        f"  🧠 Style: *{recs['learning_style']}*\n"
        f"  💪 Determination: *{determination}* "
        f"({skipped}/{total} skipped)\n"
        f"  🔴 Weakest area: *{weak_sec}*\n\n"
        f"📅 *Your Personalised Week 1 Plan*\n"
        f"  ⏱️ Daily target: *{recs['daily_hours']}h/day*\n"
        f"  ⏲️ Block length: *{recs['block_len']} minutes*\n"
        f"  📌 Focus: Remediation on {weak_sec}\n\n"
        f"_Use `/today` to see your personalised study plan!_\n"
        f"_Use `/profile` to view your full capability snapshot._"
    )
    await bot.send_message(state['chat_id'], msg, parse_mode="Markdown")


def has_active_diagnostic(user_id: int) -> bool:
    return user_id in _active_diagnostics


def is_diagnostic_callback(data: str) -> bool:
    return data.startswith("diag:")
