"""
bot.py - RPSC School Lecturer Biology Study Bot (@RPSCstudy_bot)
Run: python bot.py

UX Design:
- Only 5 slash commands exposed (/start /today /done /mock /help)
- Everything else driven by dynamic inline buttons
- User manual + quick-start shown on first /start
"""
import sys
import io
# Force UTF-8 output on Windows
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio
import logging
import os
import re
from datetime import date

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, BotCommand
)
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

from config import BOT_TOKEN
from db import (
    init_db, get_or_create_user, get_today_stats,
    log_session, mark_block_done, mark_block_skipped,
    compute_weak_topics, get_streak, get_today_plan,
    is_onboarded, get_user_profile, save_calibration,
    update_user_routine, start_block_session, clear_active_session
)
from planning import (
    generate_daily_plan, format_plan_message,
    format_block_message, get_exam_countdown,
    format_profile_message
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from datetime import datetime
from syllabus import get_syllabus_summary, get_books_list
from questions import start_mock, handle_mock_answer, format_mock_history, has_active_mock
from diagnostic import (
    start_diagnostic, handle_diagnostic_answer,
    has_active_diagnostic, is_diagnostic_callback
)
from reports import generate_daily_report
from scheduler import setup_scheduler, register_user_for_notifications

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rpsc_bot")

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ════════════════════════════════════════════════════════════════════════════
# KEYBOARD BUILDERS — All navigation via inline buttons
# ════════════════════════════════════════════════════════════════════════════

def kb_main_menu() -> InlineKeyboardMarkup:
    """Primary home menu — 5 clear action categories."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Today's Plan",  callback_data="menu:today"),
            InlineKeyboardButton(text="⏭️ Next Block",    callback_data="menu:next"),
        ],
        [
            InlineKeyboardButton(text="✅ Log Done",      callback_data="menu:done_prompt"),
            InlineKeyboardButton(text="⏩ Skip Block",    callback_data="menu:skip"),
        ],
        [
            InlineKeyboardButton(text="🎯 Mock Test",     callback_data="menu:mock"),
            InlineKeyboardButton(text="📊 My Stats",      callback_data="menu:stats"),
        ],
        [
            InlineKeyboardButton(text="🔴 Weak Topics",   callback_data="menu:weak"),
            InlineKeyboardButton(text="👤 My Profile",    callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton(text="📚 Free Books",    callback_data="menu:books"),
            InlineKeyboardButton(text="📄 PDF Report",    callback_data="menu:report"),
        ],
        [
            InlineKeyboardButton(text="❓ Help & Manual", callback_data="menu:help"),
        ],
    ])


def kb_after_plan() -> InlineKeyboardMarkup:
    """Shown after viewing today's plan."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏭️ Start Next Block", callback_data="menu:next"),
            InlineKeyboardButton(text="🎯 Quick Mock",       callback_data="menu:mock_mini"),
        ],
        [
            InlineKeyboardButton(text="📊 My Stats",         callback_data="menu:stats"),
            InlineKeyboardButton(text="🏠 Home Menu",        callback_data="menu:home"),
        ],
    ])


def kb_after_block(has_started: bool = False) -> InlineKeyboardMarkup:
    """Shown after showing next block."""
    if not has_started:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Start This Block", callback_data="menu:block_start")],
            [InlineKeyboardButton(text="⏩ Skip This Block",  callback_data="menu:skip")],
            [InlineKeyboardButton(text="🏠 Home Menu",        callback_data="menu:home")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Finish Block",      callback_data="menu:block_finish")],
            [InlineKeyboardButton(text="🏠 Home (In-Progress)", callback_data="menu:home")],
        ])


def kb_done_score() -> InlineKeyboardMarkup:
    """Score picker after marking done."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="😊 Good (8/10+)",    callback_data="score:8:10"),
            InlineKeyboardButton(text="🙂 Ok (6/10)",       callback_data="score:6:10"),
        ],
        [
            InlineKeyboardButton(text="😐 Low (4/10)",      callback_data="score:4:10"),
            InlineKeyboardButton(text="😔 Poor (2/10)",     callback_data="score:2:10"),
        ],
        [
            InlineKeyboardButton(text="⏭️ Skip Score Entry", callback_data="score:0:0"),
        ],
    ])


def kb_mock_options() -> InlineKeyboardMarkup:
    """Mock test type selector."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔬 Paper II — Biology (15 Q)", callback_data="mock_start:paper2:15"),
        ],
        [
            InlineKeyboardButton(text="🏛️ Paper I — GK & Rajasthan (10 Q)", callback_data="mock_start:paper1:10"),
        ],
        [
            InlineKeyboardButton(text="⚡ Mini Mock — 5 Quick Qs",   callback_data="mock_start:mini:5"),
        ],
        [
            InlineKeyboardButton(text="🔙 Back to Menu",             callback_data="menu:home"),
        ],
    ])


def kb_after_stats() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Today's Plan", callback_data="menu:today"),
            InlineKeyboardButton(text="⏭️ Next Block",   callback_data="menu:next"),
        ],
        [
            InlineKeyboardButton(text="📄 Get PDF Report", callback_data="menu:report"),
            InlineKeyboardButton(text="🏠 Home Menu",      callback_data="menu:home"),
        ],
    ])


def kb_home() -> InlineKeyboardMarkup:
    """Compact home button."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Back to Menu", callback_data="menu:home")]
    ])


# ════════════════════════════════════════════════════════════════════════════
# USER MANUAL TEXT
# ════════════════════════════════════════════════════════════════════════════
USER_MANUAL = """
📖 *RPSC Study Bot — Quick User Manual*

━━━━━━━━━━━━━━━━━━━━
🚀 *How to Use (Daily Routine)*
━━━━━━━━━━━━━━━━━━━━

*1. Morning (7 AM)*
Bot auto-sends your day's plan.
Or tap *📅 Today's Plan* anytime.

*2. Start a Block*
Tap *⏭️ Next Block* to see what to study next.
It shows the topic, book, and free PDF link.

*3. After Studying*
Tap *✅ Log Done* → pick minutes studied → pick your score.
This trains the AI to adapt your plan!

*4. Mock Tests*
Tap *🎯 Mock Test* → choose Paper I / II / Mini.
Negative marking: ➕1 correct ➖1/3 wrong.

*5. Night (10 PM)*
Bot auto-sends your PDF report + 5Q calibration test.
AI adjusts tomorrow's hours based on today's performance.

━━━━━━━━━━━━━━━━━━━━
⌨️ *Only 5 Commands You Need*
━━━━━━━━━━━━━━━━━━━━

`/start`  — First run / go home
`/today`  — Today's study plan
`/done 90 8/10` — Log 90 min, score 8 out of 10
`/mock`   — Start a mock test
`/help`   — This manual

━━━━━━━━━━━━━━━━━━━━
🤖 *How the AI Adapts*
━━━━━━━━━━━━━━━━━━━━

• *Day 1:* Takes 30Q diagnostic → sets your personalised hours
• *Daily:* Analyses your accuracy → boosts weak topics
• *Monthly:* Detects burnout → auto-reduces load

━━━━━━━━━━━━━━━━━━━━
📊 *Study Plan Breakdown (10.5h/day)*
━━━━━━━━━━━━━━━━━━━━

🔬 Paper II Biology → 6.5h (65%)
🏛️ Paper I GK       → 2h
✅ MCQ Practice      → 1.5h
📝 Review & Notes    → 0.5h

━━━━━━━━━━━━━━━━━━━━
🔔 *Automatic Notifications*
━━━━━━━━━━━━━━━━━━━━

🌅 7:00 AM — Morning briefing + plan
😤 2:00 PM — Nag if you've studied < 2h
🌙 10:00 PM — PDF report + calibration test
class RoutineStates(StatesGroup):
    WAKE_UP = State()
    LUNCH   = State()
    SNACK   = State()
    DINNER  = State()


# ════════════════════════════════════════════════════════════════════════════
# /start — Onboard new users with diagnostic; returning users see home
# ════════════════════════════════════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext) -> None:
    uid  = msg.from_user.id
    user = await get_or_create_user(
        uid,
        msg.from_user.username or "",
        msg.from_user.first_name or "Student"
    )
    register_user_for_notifications(uid, user['first_name'])
    onboarded = await is_onboarded(uid)

    if not onboarded:
        # ── NEW USER: show manual first, then start diagnostic ────────────
        await msg.answer(
            f"🎓 *Welcome, {user['first_name']}!*\n\n"
            f"I'm your *RPSC School Lecturer (Biology)* AI study coach.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *What I do for you:*\n"
            f"  📅 Build a personalised 10.5h/day plan\n"
            f"  🤖 Adapt it daily based on your performance\n"
            f"  🎯 Mock tests with 1/3 negative marking\n"
            f"  📄 Nightly PDF progress reports\n"
            f"  🔗 FREE NCERT PDF links for every topic\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⌨️ *You only need 5 commands:*\n"
            f"`/start` `/today` `/done` `/mock` `/help`\n\n"
            f"_Everything else is just tap a button!_ 👆\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 *First: Personal Routine Setup*\n"
            f"Tell me your times so I can build a plan without interruptions.\n\n"
            f"⏰ *What time do you Wake up?* (e.g., 06:00, 07:30)",
            parse_mode="Markdown"
        )
        await state.set_state(RoutineStates.WAKE_UP)
    else:
        # ── RETURNING USER: home screen ────────────────────────────────────
        streak    = await get_streak(uid)
        countdown = await get_exam_countdown()
        profile   = await get_user_profile(uid)
        daily_h   = profile['recommended_daily_hours'] if profile else 10.5

        await msg.answer(
            f"👋 *Welcome back, {user['first_name']}!*\n\n"
            f"🔥 Streak: *{streak} days* | ⏱️ Target: *{daily_h}h today*\n"
            f"{countdown}\n\n"
            f"_What would you like to do?_",
            parse_mode="Markdown",
            reply_markup=kb_main_menu()
        )

# ── ROUTINE HANDLERS ────────────────────────────────────────────────────────
@dp.message(RoutineStates.WAKE_UP)
async def process_wake_up(msg: Message, state: FSMContext) -> None:
    await state.update_data(wake_up=msg.text)
    await msg.answer("🍱 *Lunch time?* (e.g., 13:00, 14:00)")
    await state.set_state(RoutineStates.LUNCH)

@dp.message(RoutineStates.LUNCH)
async def process_lunch(msg: Message, state: FSMContext) -> None:
    await state.update_data(lunch=msg.text)
    await msg.answer("☕ *Evening Snack/Tea time?* (e.g., 17:00, 18:00)")
    await state.set_state(RoutineStates.SNACK)

@dp.message(RoutineStates.SNACK)
async def process_snack(msg: Message, state: FSMContext) -> None:
    await state.update_data(snack=msg.text)
    await msg.answer("🌙 *Dinner time?* (e.g., 20:30, 21:00)")
    await state.set_state(RoutineStates.DINNER)

@dp.message(RoutineStates.DINNER)
async def process_dinner(msg: Message, state: FSMContext) -> None:
    data = await state.get_data()
    data['dinner'] = msg.text
    await update_user_routine(msg.from_user.id, data)
    await state.clear()
    await msg.answer(
        "✅ *Routine saved!*\n\n"
        "🎯 *Now: 30-Question Baseline Test*\n"
        "Takes ~15 min. Sets your diagnostic profile.\n"
        "_Starting in 3 seconds…_",
        parse_mode="Markdown"
    )
    await asyncio.sleep(3)
    await start_diagnostic(msg.from_user.id, bot, msg.chat.id)


# ════════════════════════════════════════════════════════════════════════════
# /today — shortcut
# ════════════════════════════════════════════════════════════════════════════
@dp.message(Command("today"))
async def cmd_today_shortcut(msg: Message) -> None:
    await _show_today_plan(msg.from_user.id, msg.chat.id)


# ════════════════════════════════════════════════════════════════════════════
# /done — shortcut  e.g.  /done 90 8/10
# ════════════════════════════════════════════════════════════════════════════
@dp.message(Command("done"))
async def cmd_done_shortcut(msg: Message) -> None:
    await msg.answer(
        "🚫 *Manual logging is disabled.*\n\n"
        "To ensure RPSC selection, we now use *Strict Time Tracking*.\n"
        "1. Tap `⏭️ Next Block` to see your topic.\n"
        "2. Tap `🚀 Start This Block` when you begin.\n"
        "3. Tap `✅ Finish Block` only after you complete the time.\n\n"
        "_This helps the AI build a better plan for you!_",
        parse_mode="Markdown"
    )


# ════════════════════════════════════════════════════════════════════════════
# /mock — shortcut
# ════════════════════════════════════════════════════════════════════════════
@dp.message(Command("mock"))
async def cmd_mock_shortcut(msg: Message) -> None:
    uid = msg.from_user.id
    if has_active_mock(uid) or has_active_diagnostic(uid):
        await bot.send_message(msg.chat.id, "⚠️ Complete your current test first!")
        return
    await bot.send_message(
        msg.chat.id,
        "🎯 *Choose your mock test:*",
        parse_mode="Markdown",
        reply_markup=kb_mock_options()
    )


# ════════════════════════════════════════════════════════════════════════════
# /help — user manual
# ════════════════════════════════════════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(msg: Message) -> None:
    await msg.answer(USER_MANUAL, parse_mode="Markdown", reply_markup=kb_home())


# ════════════════════════════════════════════════════════════════════════════
# MASTER CALLBACK HANDLER — all buttons route here
# ════════════════════════════════════════════════════════════════════════════
@dp.callback_query()
async def on_callback(cb: CallbackQuery) -> None:
    data = cb.data or ""
    uid  = cb.from_user.id
    cid  = cb.message.chat.id

    # ── Diagnostic answers ────────────────────────────────────────────────
    if is_diagnostic_callback(data):
        if has_active_diagnostic(uid):
            await handle_diagnostic_answer(cb, bot)
        else:
            await cb.answer("Diagnostic not active.", show_alert=True)
        return

    # ── Mock answers ──────────────────────────────────────────────────────
    if data.startswith("mock:"):
        await handle_mock_answer(cb, bot)
        return

    # ── Mock start picker ─────────────────────────────────────────────────
    if data.startswith("mock_start:"):
        _, mode, num_str = data.split(":")
        num = int(num_str)
        if has_active_mock(uid) or has_active_diagnostic(uid):
            await cb.answer("Complete your current test first!", show_alert=True)
            return
        if mode == "paper1":
            paper, section = 1, "History"
            label = "Paper I Mock — GK & Rajasthan"
        elif mode == "mini":
            paper, section = 2, None
            label = "Mini Mock — 5 Questions"
        else:
            paper, section = 2, None
            label = "Paper II Mock — Biology"
        await cb.message.edit_reply_markup(reply_markup=None)
        await bot.send_message(
            cid,
            f"🚀 *{label}*\n{num} questions | ➕+1 ➖-1/3\n_Answer with the buttons below each question._",
            parse_mode="Markdown"
        )
        await start_mock(uid, bot, cid, paper=paper, section=section, num_questions=num)
        await cb.answer()
        return

    # ── Quick done from block buttons  done:<minutes>:<correct>:<total> ───
    if data.startswith("done:"):
        parts   = data.split(":")
        minutes = int(parts[1])
        correct = int(parts[2])
        total_q = int(parts[3])
        await cb.message.edit_reply_markup(reply_markup=None)
        if total_q == 0:
            # Ask for score
            _pending_done[uid] = minutes
            await bot.send_message(
                cid,
                f"✅ *{minutes} min logged!*\nHow did you score?",
                parse_mode="Markdown",
                reply_markup=kb_done_score()
            )
        else:
            await _log_done(uid, cid, minutes, correct, total_q)
        await cb.answer()
        return

    # ── Score picker ──────────────────────────────────────────────────────
    if data.startswith("score:"):
        parts   = data.split(":")
        correct = int(parts[1])
        total_q = int(parts[2])
        minutes = _pending_done.pop(uid, 60)
        await cb.message.edit_reply_markup(reply_markup=None)
        await _log_done(uid, cid, minutes, correct, total_q)
        await cb.answer()
        return

    # ── Menu actions ──────────────────────────────────────────────────────
    if data.startswith("menu:"):
        action = data.split(":")[1]
        await cb.message.edit_reply_markup(reply_markup=None)

        if action == "home":
            profile = await get_user_profile(uid)
            daily_h = profile['recommended_daily_hours'] if profile else 10.5
            streak  = await get_streak(uid)
            await bot.send_message(
                cid,
                f"🏠 *Home Menu*\n🔥 Streak: *{streak} days* | ⏱️ Target: *{daily_h}h*",
                parse_mode="Markdown",
                reply_markup=kb_main_menu()
            )

        elif action == "today":
            await _show_today_plan(uid, cid)

        elif action == "next":
            await _show_next_block(uid, cid)

        elif action == "block_start":
            plan    = await get_today_plan(uid)
            pending = [b for b in plan if b.get('status') == 'pending']
            if not pending:
                await cb.answer("No pending blocks.", show_alert=True)
                return
            
            block_idx = pending[0]['block_index']
            await start_block_session(uid, block_idx)
            await bot.send_message(
                cid,
                f"🚀 *Block Started!* ⏱️\n"
                f"Stay away from distractions. I'll be waiting for you to finish.",
                parse_mode="Markdown",
                reply_markup=kb_after_block(has_started=True)
            )

        elif action == "block_finish":
            # Check elapsed time vs block target
            profile = await get_user_profile(uid)
            if not profile or not profile.get('active_block_start'):
                await cb.answer("You didn't start the block!", show_alert=True)
                return
            
            start_dt = datetime.fromisoformat(profile['active_block_start'])
            elapsed  = (datetime.now() - start_dt).total_seconds() / 60
            
            plan    = await get_today_plan(uid)
            pending = [b for b in plan if b.get('status') == 'pending' and b['block_index'] == profile['active_block_index']]
            if not pending:
                await cb.answer("Session error.", show_alert=True)
                return
            
            target_min = pending[0]['hours'] * 60
            if elapsed < (target_min * 0.9): # 10% grace period
                remaining = int(target_min - elapsed)
                await bot.send_message(
                    cid,
                    f"⚠️ *Discipline Alert!* 😤\n\n"
                    f"You have only studied for *{int(elapsed)} minutes*.\n"
                    f"This block requires *{int(target_min)} minutes*.\n\n"
                    f"RPSC selection is for those who are honest with themselves. "
                    f"Go back and finish the remaining *{remaining} minutes*!",
                    parse_mode="Markdown",
                    reply_markup=kb_after_block(has_started=True)
                )
            else:
                # Success!
                _pending_done[uid] = int(elapsed)
                await clear_active_session(uid)
                await bot.send_message(
                    cid,
                    f"🎊 *Great Discipline!* You spent {int(elapsed)} mins.\n"
                    f"How did you score in your self-assessment?",
                    parse_mode="Markdown",
                    reply_markup=kb_done_score()
                )

        elif action == "done_prompt":
            profile = await get_user_profile(uid)
            if profile and profile.get('active_block_index') != -1:
                # Redirect to finish block
                await bot.send_message(
                    cid, "📌 You have an active block running. Finish it first!",
                    reply_markup=kb_after_block(has_started=True)
                )
            else:
                await bot.send_message(
                    cid, "❌ Start a block using 'Home' -> 'Next Block' first to log time accurately.",
                    reply_markup=kb_home()
                )

        elif action == "skip":
            profile = await get_user_profile(uid)
            plan    = await get_today_plan(uid)
            pending = [b for b in plan if b.get('status') == 'pending']
            
            if not pending:
                await bot.send_message(cid, "❌ No pending blocks to skip.")
                return

            # Strict Skip Rule: Only in first 10 mins
            if profile and profile.get('active_block_start'):
                start_dt = datetime.fromisoformat(profile['active_block_start'])
                elapsed  = (datetime.now() - start_dt).total_seconds() / 60
                if elapsed > 10:
                    await bot.send_message(
                        cid, 
                        f"🛑 *Skip Denied!* 😤\n\n"
                        f"You started this block {int(elapsed)} minutes ago. "
                        f"You can only skip a block within the first 10 minutes.\n\n"
                        f"Finish what you started! RPSC selection depends on this.",
                        parse_mode="Markdown",
                        reply_markup=kb_after_block(has_started=True)
                    )
                    return

            block_idx = pending[0].get('block_index', 0)
            label     = pending[0].get('label', 'Block')
            await mark_block_skipped(uid, block_idx)
            await clear_active_session(uid)
            await bot.send_message(
                cid,
                f"⏭️ *Skipped:* {label}\n\n"
                f"⚠️ The AI tracks your skips — too many reduce your score!\n"
                f"Tap Next Block to continue.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="⏭️ Next Block",  callback_data="menu:next"),
                    InlineKeyboardButton(text="🏠 Home",        callback_data="menu:home"),
                ]])
            )

        elif action == "stats":
            await _show_stats(uid, cid)

        elif action == "weak":
            await _show_weak(uid, cid)

        elif action == "profile":
            text = await format_profile_message(uid)
            await bot.send_message(
                cid, text, parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=kb_home()
            )

        elif action == "books":
            text = await get_books_list()
            await bot.send_message(
                cid, text, parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=kb_home()
            )

        elif action == "report":
            name = cb.from_user.first_name or "Student"
            await bot.send_message(cid, "⚙️ Generating your PDF report…")
            try:
                pdf_path = await generate_daily_report(uid, name)
                with open(pdf_path, 'rb') as f:
                    await bot.send_document(
                        cid, f,
                        caption=f"📄 RPSC Report — {date.today().strftime('%d %b %Y')}",
                    )
            except Exception as e:
                log.error(f"Report error: {e}")
                await bot.send_message(
                    cid,
                    "⚠️ Log study sessions with ✅ Done first, then try again.",
                    reply_markup=kb_home()
                )

        elif action == "mock":
            await bot.send_message(
                cid,
                "🎯 *Choose your mock test:*",
                parse_mode="Markdown",
                reply_markup=kb_mock_options()
            )

        elif action == "mock_mini":
            if has_active_mock(uid):
                await bot.send_message(cid, "⚠️ Complete your current test first!")
            else:
                await bot.send_message(
                    cid,
                    "⚡ *Mini Mock — 5 Questions*\n➕+1 ➖-1/3",
                    parse_mode="Markdown"
                )
                await start_mock(uid, bot, cid, num_questions=5)

        elif action == "help":
            await bot.send_message(
                cid, USER_MANUAL, parse_mode="Markdown",
                reply_markup=kb_home()
            )

        await cb.answer()
        return

    await cb.answer("Unknown action", show_alert=True)


# ════════════════════════════════════════════════════════════════════════════
# CORE ACTION HELPERS
# ════════════════════════════════════════════════════════════════════════════

# Temp store for pending done minutes (awaiting score)
_pending_done: dict[int, int] = {}


async def _show_today_plan(uid: int, cid: int) -> None:
    blocks  = await get_today_plan(uid)
    profile = await get_user_profile(uid)
    daily_h = profile['recommended_daily_hours'] if profile else 10.5

    if not blocks:
        await bot.send_message(cid, "⚙️ Building your personalised plan…")
        blocks = await generate_daily_plan(uid)

    plan_txt  = await format_plan_message(blocks, daily_hours=daily_h)
    countdown = await get_exam_countdown()
    await bot.send_message(
        cid,
        plan_txt + f"\n\n{countdown}",
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb_after_plan()
    )


async def _show_next_block(uid: int, cid: int) -> None:
    plan = await get_today_plan(uid)
    if not plan:
        plan = await generate_daily_plan(uid)
        plan = await get_today_plan(uid)

    pending = [b for b in plan if b.get('status') == 'pending']
    if not pending:
        await bot.send_message(
            cid,
            "🎉 *All blocks done for today!*\nAmazing work — use the button below to get your report.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📄 Get PDF Report", callback_data="menu:report"),
                InlineKeyboardButton(text="🏠 Home",           callback_data="menu:home"),
            ]])
        )
        return

    next_b    = pending[0]
    block_num = next_b.get('block_index', 0) + 1
    text      = await format_block_message(next_b, block_num)
    await bot.send_message(
        cid, text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb_after_block()
    )


async def _show_stats(uid: int, cid: int) -> None:
    stats     = await get_today_stats(uid)
    streak    = await get_streak(uid)
    countdown = await get_exam_countdown()
    profile   = await get_user_profile(uid)
    daily_h   = profile['recommended_daily_hours'] if profile else 10.5

    filled = int((stats['total_hours'] / daily_h) * 10)
    bar    = "🟩" * min(filled, 10) + "⬜" * max(0, 10 - filled)

    await bot.send_message(
        cid,
        f"📊 *Today's Stats — {date.today().strftime('%d %b %Y')}*\n\n"
        f"⏱️ Hours: *{stats['total_hours']}h / {daily_h}h*\n"
        f"{bar}\n\n"
        f"✅ Questions: *{stats['total_q']}* | Correct: *{stats['total_correct']}*\n"
        f"📈 Accuracy: *{stats['accuracy']}%*\n"
        f"📋 Blocks: *{stats['plan_done']}/{stats['plan_total']} done*\n"
        f"🔥 Streak: *{streak} days*\n\n"
        f"{countdown}",
        parse_mode="Markdown",
        reply_markup=kb_after_stats()
    )


async def _show_weak(uid: int, cid: int) -> None:
    weak = await compute_weak_topics(uid)
    if not weak:
        await bot.send_message(
            cid,
            "🏆 *No weak topics!*\n"
            "Keep logging sessions to enable AI tracking.",
            parse_mode="Markdown",
            reply_markup=kb_home()
        )
        return

    lines = ["🔴 *Weak Topics* _(< 60% done OR < 50% accurate)_\n"]
    for i, w in enumerate(weak, 1):
        c = "🟥" if w['completion_pct'] < 40 else "🟧" if w['completion_pct'] < 60 else "🟨"
        a = "🟥" if w['accuracy_pct'] < 30  else "🟧" if w['accuracy_pct'] < 50  else "🟨"
        lines.append(
            f"*{i}. {w['name']}*\n"
            f"  {c} Done: {w['completion_pct']}% | {a} Accuracy: {w['accuracy_pct']}%\n"
            f"  🔗 [Revise PDF]({w.get('free_pdf_link','#')})\n"
        )
    lines.append("_AI will auto-boost these topics tomorrow!_ 🤖")
    await bot.send_message(
        cid, "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=kb_home()
    )


async def _log_done(uid: int, cid: int, minutes: int,
                    correct: int, total_q: int) -> None:
    hours = round(minutes / 60, 2)
    plan    = await get_today_plan(uid)
    pending = [b for b in plan if b.get('status') == 'pending']
    topic_id = None
    if pending:
        topic_id  = pending[0].get('topic_id')
        block_idx = pending[0].get('block_index', 0)
        await mark_block_done(uid, block_idx)

    await log_session(uid, topic_id, hours, total_q, correct)

    from db import update_streak
    stats   = await get_today_stats(uid)
    streak  = await update_streak(uid, stats['total_hours'])
    profile = await get_user_profile(uid)
    daily_h = profile['recommended_daily_hours'] if profile else 10.5

    pct      = round(correct / total_q * 100) if total_q > 0 else 0
    verdict  = "🏆 Excellent!" if pct >= 80 else \
               "✅ Good job!"  if pct >= 60 else \
               "⚠️ Needs work" if pct >= 40 else \
               "📚 Revise this topic!" if total_q > 0 else ""

    filled   = int((stats['total_hours'] / daily_h) * 10)
    bar      = "🟩" * min(filled, 10) + "⬜" * max(0, 10 - filled)

    score_line = f"📝 Score: *{correct}/{total_q}* ({pct}%)\n" if total_q > 0 else ""

    await bot.send_message(
        cid,
        f"✅ *Block Logged!*\n\n"
        f"⏱️ Time: *{minutes} min*\n"
        f"{score_line}"
        f"📊 Today: *{stats['total_hours']}h / {daily_h}h*\n"
        f"{bar}\n"
        f"🔥 Streak: *{streak} days*\n\n"
        f"{verdict}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⏭️ Next Block",  callback_data="menu:next"),
                InlineKeyboardButton(text="📊 Stats",       callback_data="menu:stats"),
            ],
            [
                InlineKeyboardButton(text="🎯 Quick Mock",  callback_data="menu:mock_mini"),
                InlineKeyboardButton(text="🏠 Home",        callback_data="menu:home"),
            ],
        ])
    )


# ════════════════════════════════════════════════════════════════════════════
# Fallback for any typed message
# ════════════════════════════════════════════════════════════════════════════
@dp.message()
async def cmd_fallback(msg: Message) -> None:
    await msg.answer(
        "👇 Use the buttons or type /help",
        reply_markup=kb_main_menu()
    )


# ════════════════════════════════════════════════════════════════════════════
# STARTUP
# ════════════════════════════════════════════════════════════════════════════
# ── Keep-Alive Web Server for Hosting ─────────────────────────────────────────
def run_health_check_server():
    from http.server import BaseHTTPRequestHandler, HTTPServer
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is Healthy and Running!")
        def log_message(self, *args): pass

    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info(f"🌐 Keep-Alive server active on port {port}")
    server.serve_forever()


async def on_startup() -> None:
    log.info("RPSC Study Bot starting...")
    os.makedirs("data",    exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    await init_db()

    # Start Health Check Server in a thread
    import threading
    threading.Thread(target=run_health_check_server, daemon=True).start()

    # Only 5 commands shown in the Telegram menu — keeps it clean
    await bot.set_my_commands([
        BotCommand(command="start", description="Home menu / restart"),
        BotCommand(command="today", description="See today's study plan"),
        BotCommand(command="done",  description="Log done: /done 90 8/10"),
        BotCommand(command="mock",  description="Start a mock test"),
        BotCommand(command="help",  description="User manual & guide"),
    ])
    setup_scheduler(bot)
    log.info("Bot ready! Polling started.")


async def main() -> None:
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set in .env file!")
        return
    dp.startup.register(on_startup)
    log.info("Bot polling started. Press Ctrl+C to stop.")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
