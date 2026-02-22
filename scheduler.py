"""
scheduler.py - Persistent multi-user APScheduler jobs for RPSC Study Bot.
Fetches all students from the DB on every job run to ensure 24/7 coverage.
"""
import asyncio
import logging
from datetime import datetime, date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot

from config import (
    MORNING_BRIEFING_HOUR, MORNING_BRIEFING_MINUTE,
    NIGHT_SUMMARY_HOUR, NIGHT_SUMMARY_MINUTE,
    TIMEZONE, ADMIN_CHAT_ID
)

log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)


async def _get_all_users() -> list:
    """Fetch all users from the DB safely."""
    import aiosqlite
    from config import DB_PATH
    users = []
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT user_id, first_name FROM users")
            users = [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        log.error(f"Failed to fetch users for scheduler: {e}")
    return users


def register_user_for_notifications(user_id: int, first_name: str) -> None:
    """Placeholder: no longer needed as we query DB directly."""
    pass


# ── Job helpers ───────────────────────────────────────────────────────────────
async def _morning_briefing(bot: Bot) -> None:
    """7 AM daily briefing for ALL registered students."""
    from planning import generate_daily_plan, format_plan_message, get_exam_countdown
    from db import get_streak, get_user_profile

    users = await _get_all_users()
    for u in users:
        uid = u['user_id']
        name = u['first_name']
        try:
            profile = await get_user_profile(uid)
            h = profile['recommended_daily_hours'] if profile else 10.5
            streak   = await get_streak(uid)
            blocks   = await generate_daily_plan(uid)
            plan_msg = await format_plan_message(blocks, daily_hours=h)
            countdown = await get_exam_countdown()
            
            greeting = (
                f"🌅 *Good Morning, {name}!* 📖\n"
                f"🔥 Streak: *{streak} days*\n"
                f"{countdown}\n\n"
                f"Today's personalised target: *{h}h*\n\n"
                + plan_msg
            )
            await bot.send_message(uid, greeting, parse_mode="Markdown",
                                   disable_web_page_preview=True)
        except Exception as e:
            log.error(f"Morning briefing failed for {uid}: {e}")


async def _night_summary(bot: Bot) -> None:
    """10 PM nightly summary for ALL active students."""
    from db import get_today_stats, update_streak, save_calibration
    from reports import generate_daily_report
    from questions import start_mock
    
    users = await _get_all_users()
    for u in users:
        uid = u['user_id']
        name = u['first_name']
        try:
            stats  = await get_today_stats(uid)
            
            # Skip if they logged nothing today (no annoying empty reports)
            if stats['total_hours'] == 0 and stats['total_q'] == 0:
                continue

            streak = await update_streak(uid, stats['total_hours'])

            # --- AI Calibration: auto-adjust next day based on performance ---
            accuracy_frac     = stats['accuracy'] / 100.0
            plan_completion   = (stats['plan_done'] / stats['plan_total']
                                 if stats['plan_total'] > 0 else 0)
            cal_result = await save_calibration(
                user_id        = uid,
                accuracy       = accuracy_frac,
                completion_rate = plan_completion,
                actual_hours   = stats['total_hours'],
                questions_done = stats['total_q'],
                correct        = stats['total_correct'],
            )

            msg = (
                f"🌙 *Good Night, {name}!*\n\n"
                f"📊 *Today's Summary:*\n"
                f"  ⏱️ Hours: *{stats['total_hours']}h*\n"
                f"  ✅ Questions: *{stats['total_q']}* (Accuracy: {stats['accuracy']}%)\n"
                f"  📋 Blocks: *{stats['plan_done']}/{stats['plan_total']} done*\n"
                f"  🔥 Streak: *{streak} days*\n\n"
            )
            if cal_result.get('adjustment_msg'):
                msg += f"🤖 *AI Adjustment:* {cal_result['adjustment_msg']}\n\n"

            msg += "\n_Generating your PDF report…_"
            await bot.send_message(uid, msg, parse_mode="Markdown")

            pdf_path = await generate_daily_report(uid, name)
            with open(pdf_path, 'rb') as f:
                await bot.send_document(
                    uid, f,
                    caption=(
                        f"📄 Daily Report — {date.today().strftime('%d %b %Y')}\n"
                        f"New target: {cal_result['new_hours']}h tomorrow"
                    )
                )
            
            # Nightly 5Q Calibration micro-test
            await asyncio.sleep(2)
            await bot.send_message(
                uid,
                "🧪 *Nightly Calibration — 5 Quick Questions*\n"
                "_Answer to help the AI fine-tune tomorrow!_",
                parse_mode="Markdown"
            )
            await start_mock(uid, bot, uid, num_questions=5)

        except Exception as e:
            log.error(f"Night summary failed for {uid}: {e}")


async def _block_reminder(bot: Bot) -> None:
    """Placeholder reminder job."""
    pass


async def _motivational_nag(bot: Bot) -> None:
    """2 PM nag check for students who missed their target."""
    from db import get_today_stats
    users = await _get_all_users()
    for u in users:
        uid = u['user_id']
        name = u['first_name']
        try:
            stats = await get_today_stats(uid)
            if stats['total_hours'] < 2.0:
                nags = [
                    f"😤 {name}! Only {stats['total_hours']}h studied by 2 PM?! Move it!",
                    f"🔴 {name}, your competition studied 5h already! You? {stats['total_hours']}h!",
                    f"⚡ {name}, RPSC selection rewards sweat, not sleep. Back to work!",
                ]
                import random
                await bot.send_message(uid, random.choice(nags), parse_mode="Markdown")
        except Exception as e:
            log.error(f"Nag failed for {uid}: {e}")


async def _admin_daily_report(bot: Bot) -> None:
    """Send a global leadership summary to the admin."""
    from db import get_admin_leaderboard
    if not ADMIN_CHAT_ID:
        return

    try:
        data = await get_admin_leaderboard()
        lines = [
            f"👑 *RPSC Study Bot — Admin Daily Dashboard*",
            f"📅 {date.today().strftime('%d %B %Y')}\n",
            f"🏆 *Top Performers (Most Hours)*"
        ]
        for i, u in enumerate(data['top'], 1):
            acc = int(u.get('acc', 0) or 0)
            lines.append(f"  {i}. {u['first_name']}: *{u['total_h']}h* ({acc}% acc)")
        
        lines.append(f"\n✅ *On Track (High Adherence)*")
        for i, u in enumerate(data['on_track'], 1):
            lines.append(f"  {i}. {u['first_name']}: *{u['done_blocks']} blocks* done")

        lines.append(f"\n🛑 *Attention Needed (Low Study)*")
        for i, u in enumerate(data['low'], 1):
            lines.append(f"  {i}. {u['first_name']}: *{u['total_h']}h today*")

        lines.append(f"\n_Keep motivating them! RPSC selection guarantees await._")
        
        await bot.send_message(ADMIN_CHAT_ID, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        log.error(f"Admin report failed: {e}")


# ── Scheduler setup ───────────────────────────────────────────────────────────
def setup_scheduler(bot: Bot) -> None:
    """Register all scheduled jobs."""

    scheduler.add_job(
        _morning_briefing,
        CronTrigger(hour=MORNING_BRIEFING_HOUR,
                    minute=MORNING_BRIEFING_MINUTE,
                    timezone=TIMEZONE),
        args=[bot],
        id="morning_briefing",
        replace_existing=True,
    )

    scheduler.add_job(
        _night_summary,
        CronTrigger(hour=NIGHT_SUMMARY_HOUR,
                    minute=NIGHT_SUMMARY_MINUTE,
                    timezone=TIMEZONE),
        args=[bot],
        id="night_summary",
        replace_existing=True,
    )

    scheduler.add_job(
        _motivational_nag,
        CronTrigger(hour=14, minute=0, timezone=TIMEZONE),
        args=[bot],
        id="nag_midday",
        replace_existing=True,
    )

    scheduler.add_job(
        _admin_daily_report,
        CronTrigger(hour=23, minute=0, timezone=TIMEZONE),
        args=[bot],
        id="admin_daily_report",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
    log.info("✅ Scheduler started (Multi-User Persistence ON)")
