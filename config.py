"""
config.py - Central configuration for RPSC Study Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Bot Credentials ──────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))

# ── Database (Robust for Railway Volumes) ───────────────────────────────────
DB_DIR  = os.path.join(BASE_DIR, "data")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "rpsc_bot.db")

# ── Data Files ────────────────────────────────────────────────────────────────
BIOLOGY_CSV: str   = os.path.join(DB_DIR, "biology_topics.csv")
PAPER1_CSV: str    = os.path.join(DB_DIR, "paper1_topics.csv")
QUESTIONS_JSON: str = os.path.join(DB_DIR, "questions_sample.json")

# ── Daily Study Plan (10.5 hours total) ──────────────────────────────────────
DAILY_BLOCKS = [
    {"label": "Paper II – SrSec Biology",    "paper": 2, "section": "SrSec",    "hours": 2.5, "emoji": "🔬"},
    {"label": "Paper II – Grad Biology",     "paper": 2, "section": "Grad",     "hours": 2.0, "emoji": "🧬"},
    {"label": "Paper II – Pedagogy",         "paper": 2, "section": "Pedagogy", "hours": 1.0, "emoji": "📖"},
    {"label": "Paper II – ICT",              "paper": 2, "section": "ICT",      "hours": 1.0, "emoji": "💻"},
    {"label": "Paper I – GK & Rajasthan",   "paper": 1, "section": "History",   "hours": 2.0, "emoji": "🏛️"},
    {"label": "MCQ Practice",               "paper": 0, "section": "MCQ",       "hours": 1.5, "emoji": "✅"},
    {"label": "Daily Review & Notes",       "paper": 0, "section": "Review",    "hours": 0.5, "emoji": "📝"},
]

TOTAL_STUDY_HOURS = 10.5
PAPER2_RATIO = 0.65

# ── Notification Schedule ─────────────────────────────────────────────────────
MORNING_BRIEFING_HOUR   = 7
MORNING_BRIEFING_MINUTE = 0
NIGHT_SUMMARY_HOUR   = 22
NIGHT_SUMMARY_MINUTE = 0
PRE_BLOCK_REMINDER_MINUTES = 10

# ── Weak Topic Thresholds ─────────────────────────────────────────────────────
WEAK_COMPLETION_THRESHOLD = 0.60
WEAK_ACCURACY_THRESHOLD   = 0.50

# ── Mock Test Settings ────────────────────────────────────────────────────────
NEGATIVE_MARKING_RATIO = 1 / 3
MOCK_TIME_LIMITS = {"paper1": 120, "paper2": 120, "mini": 30}

# ── Streak & Gamification ─────────────────────────────────────────────────────
STREAK_GOAL_HOURS = 8.0

# ── PDF Report ────────────────────────────────────────────────────────────────
REPORT_OUTPUT_DIR = os.path.join(BASE_DIR, "reports")
if not os.path.exists(REPORT_OUTPUT_DIR):
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
PDF_PAGE_SIZE = "A4"

# ── Timezone ──────────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"
