"""
config.py - Central configuration for RPSC Study Bot (Railway Optimized)
"""
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Bot Credentials ──────────────────────────────────────────────────────────
raw_token = os.getenv("BOT_TOKEN", "").strip()
# Remove accidental quotes if the user pasted them into Railway
if (raw_token.startswith('"') and raw_token.endswith('"')) or \
   (raw_token.startswith("'") and raw_token.endswith("'")):
    raw_token = raw_token[1:-1].strip()

BOT_TOKEN: str = raw_token
ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))

if not BOT_TOKEN:
    print("\n❌ FATAL ERROR: BOT_TOKEN is missing or empty!")
    print("Please add 'BOT_TOKEN' to your Railway Environment Variables.\n")
elif ":" not in BOT_TOKEN:
    print(f"\n❌ FATAL ERROR: BOT_TOKEN '{BOT_TOKEN[:5]}...' looks invalid (missing ':')!")

# ── Database (Mapped to Railway Volume) ─────────────────────────────────────
# We use /app/data for the Volume to keep the DB safe
DB_DIR  = os.path.join(BASE_DIR, "data")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "rpsc_bot.db")

# ── Seed Data Files (Uploaded in the repository) ───────────────────────────
# We look for them in the repository folder directly
BIOLOGY_CSV: str   = os.path.join(BASE_DIR, "data", "biology_topics.csv")
PAPER1_CSV: str    = os.path.join(BASE_DIR, "data", "paper1_topics.csv")
QUESTIONS_JSON: str = os.path.join(BASE_DIR, "data", "questions_sample.json")

# IF the volume is mounted at /app/data, it might MASK the repo's /data folder.
# So we check if the files exist, if not, we look in the root if we put them there.
if not os.path.exists(BIOLOGY_CSV):
    BIOLOGY_CSV = os.path.join(BASE_DIR, "biology_topics.csv")
    PAPER1_CSV  = os.path.join(BASE_DIR, "paper1_topics.csv")
    QUESTIONS_JSON = os.path.join(BASE_DIR, "questions_sample.json")

# ── Daily Study Plan ────────────────────────────────────────────────────────
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
# We use 'reports' folder for PDFs
REPORT_OUTPUT_DIR = os.path.join(BASE_DIR, "reports")
if not os.path.exists(REPORT_OUTPUT_DIR):
    os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)
PDF_PAGE_SIZE = "A4"

# ── Timezone ──────────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"
