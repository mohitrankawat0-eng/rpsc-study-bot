"""
questions.py - MCQ engine with 1/3 negative marking for mock tests.
"""
import asyncio
import time
from typing import Callable
from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from db import get_questions, save_mock, get_mock_history
from config import NEGATIVE_MARKING_RATIO, MOCK_TIME_LIMITS

# ── In-memory mock state ────────────────────────────────────────────────────
_active_mocks: dict[int, dict] = {}   # user_id → mock state


def _make_option_keyboard(q_index: int, options: list[str], mock_id: str) -> InlineKeyboardMarkup:
    labels = ["A", "B", "C", "D"]
    buttons = []
    for i, opt in enumerate(options):
        buttons.append([
            InlineKeyboardButton(
                text=f"{labels[i]}) {opt}",
                callback_data=f"mock:{mock_id}:{q_index}:{i}"
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="⏭️ Skip", callback_data=f"mock:{mock_id}:{q_index}:skip"),
        InlineKeyboardButton(text="🛑 End Mock", callback_data=f"mock:{mock_id}:{q_index}:end"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def start_mock(user_id: int, bot: Bot, chat_id: int,
                     paper: int | None = None,
                     section: str | None = None,
                     num_questions: int = 10) -> None:
    """Start a mock test session for the user."""
    questions = await get_questions(section=section, limit=num_questions)
    if not questions:
        await bot.send_message(chat_id, "❌ No questions available for this selection.")
        return

    mock_id = str(int(time.time()))
    _active_mocks[user_id] = {
        "mock_id":    mock_id,
        "chat_id":    chat_id,
        "paper":      paper or 2,
        "questions":  questions,
        "current":    0,
        "correct":    0,
        "wrong":      0,
        "skipped":    0,
        "start_time": time.time(),
        "answered":   {},
    }

    header = (
        f"🎯 *Mock Test Starting!*\n"
        f"📋 {len(questions)} Questions\n"
        f"➕ +1 per correct | ➖ -{NEGATIVE_MARKING_RATIO:.2f} per wrong\n"
        f"⏱️ Take your time, think before answering!\n\n"
    )
    await bot.send_message(chat_id, header, parse_mode="Markdown")
    await _send_question(bot, user_id)


async def _send_question(bot: Bot, user_id: int) -> None:
    state = _active_mocks.get(user_id)
    if not state:
        return

    idx = state['current']
    questions = state['questions']

    if idx >= len(questions):
        await _finish_mock(bot, user_id)
        return

    q = questions[idx]
    opts = [q['opt_a'], q['opt_b'], q['opt_c'], q['opt_d']]
    labels = ["A", "B", "C", "D"]
    opts_text = "\n".join(f"  *{labels[i]})* {o}" for i, o in enumerate(opts) if o)

    text = (
        f"❓ *Q{idx + 1}/{len(questions)}*\n\n"
        f"{q['question']}\n\n"
        f"{opts_text}\n\n"
        f"_Level: {q.get('level', '?').title()} | "
        f"Paper {q.get('paper', '?')}_"
    )

    kb = _make_option_keyboard(idx, [o for o in opts if o], state['mock_id'])
    await bot.send_message(state['chat_id'], text,
                           parse_mode="Markdown",
                           reply_markup=kb)


async def handle_mock_answer(callback: CallbackQuery, bot: Bot) -> None:
    """Handle answer button callback."""
    data   = callback.data  # mock:<mock_id>:<q_index>:<answer>
    parts  = data.split(":")
    if len(parts) < 4:
        return

    _, mock_id, q_index_str, answer_str = parts[0], parts[1], parts[2], parts[3]
    user_id  = callback.from_user.id
    state    = _active_mocks.get(user_id)

    if not state or state['mock_id'] != mock_id:
        await callback.answer("❌ No active mock found.", show_alert=True)
        return

    q_index = int(q_index_str)
    q = state['questions'][q_index]
    opts = [q['opt_a'], q['opt_b'], q['opt_c'], q['opt_d']]

    await callback.message.edit_reply_markup(reply_markup=None)

    if answer_str == "end":
        await callback.answer("Ending mock...")
        _active_mocks[user_id]['current'] = len(state['questions'])
        await _finish_mock(bot, user_id)
        return

    if answer_str == "skip":
        state['skipped'] += 1
        state['answered'][q_index] = 'skip'
        feedback = f"⏭️ *Q{q_index + 1} Skipped*\n✅ Correct: *{opts[q['answer_idx']]}*"
        if q.get('explanation'):
            feedback += f"\n💡 _{q['explanation']}_"
        await callback.message.reply(feedback, parse_mode="Markdown")
    else:
        chosen = int(answer_str)
        correct_idx = q['answer_idx']
        labels = ["A", "B", "C", "D"]
        if chosen == correct_idx:
            state['correct'] += 1
            state['answered'][q_index] = 'correct'
            feedback = f"✅ *Correct! +1 mark*\n📖 _{q.get('explanation', '')}_"
        else:
            state['wrong'] += 1
            state['answered'][q_index] = 'wrong'
            feedback = (
                f"❌ *Wrong! -{NEGATIVE_MARKING_RATIO:.2f} mark*\n"
                f"Your answer: *{labels[chosen]}) {opts[chosen]}*\n"
                f"✅ Correct: *{labels[correct_idx]}) {opts[correct_idx]}*\n"
                f"💡 _{q.get('explanation', '')}_"
            )
        await callback.message.reply(feedback, parse_mode="Markdown")

    await callback.answer()
    state['current'] += 1
    await asyncio.sleep(1)
    await _send_question(bot, user_id)


async def _finish_mock(bot: Bot, user_id: int) -> None:
    state = _active_mocks.pop(user_id, None)
    if not state:
        return

    total_q   = len(state['questions'])
    correct   = state['correct']
    wrong     = state['wrong']
    skipped   = state['skipped']
    attempted = correct + wrong
    time_taken = int(time.time() - state['start_time'])

    score_raw = correct
    score_net = round(correct - (wrong * NEGATIVE_MARKING_RATIO), 2)
    accuracy  = round((correct / attempted * 100) if attempted > 0 else 0, 1)

    result = await save_mock(
        user_id  = user_id,
        paper    = state['paper'],
        total_q  = total_q,
        attempted = attempted,
        correct  = correct,
        wrong    = wrong,
        time_taken = time_taken,
    )

    mins, secs = divmod(time_taken, 60)
    pct_score  = round((score_net / total_q) * 100, 1) if total_q > 0 else 0

    verdict = "🏆 Excellent!" if pct_score >= 70 else \
              "👍 Good!" if pct_score >= 50 else \
              "📚 Keep Practicing!" if pct_score >= 35 else \
              "🔴 Needs urgent revision!"

    msg = (
        f"🎯 *Mock Test Complete!*\n\n"
        f"📊 *Results*\n"
        f"  Total Qs:   {total_q}\n"
        f"  Attempted:  {attempted}\n"
        f"  ✅ Correct:  {correct}\n"
        f"  ❌ Wrong:    {wrong}\n"
        f"  ⏭️ Skipped:  {skipped}\n\n"
        f"📈 Raw Score: *{score_raw}/{total_q}*\n"
        f"📉 Net Score (−1/3): *{score_net}/{total_q}*\n"
        f"🎯 Accuracy: *{accuracy}%*\n"
        f"⏱️ Time: {mins}m {secs}s\n\n"
        f"{verdict}\n\n"
        f"_Use /report to get your detailed PDF analysis._"
    )
    await bot.send_message(state['chat_id'], msg, parse_mode="Markdown")


async def format_mock_history(user_id: int) -> str:
    history = await get_mock_history(user_id, limit=5)
    if not history:
        return "📋 No mock tests recorded yet. Use /mock to start!"

    lines = ["📊 *Recent Mock Tests*\n"]
    for i, m in enumerate(history, 1):
        pct = round((m['score_net'] / m['total_q']) * 100, 1) if m['total_q'] > 0 else 0
        lines.append(
            f"*#{i}* `{m['mock_date']}` | Paper {m['paper']}\n"
            f"  Score: {m['score_net']}/{m['total_q']} ({pct}%) | "
            f"✅{m['correct']} ❌{m['wrong']}"
        )
    return "\n".join(lines)


def has_active_mock(user_id: int) -> bool:
    return user_id in _active_mocks
