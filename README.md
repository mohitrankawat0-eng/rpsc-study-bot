# 🎓 RPSC Study Bot — `antigravity_rpsc_tutor`

**Your ruthless RPSC School Lecturer (Biology) prep companion.**

> 10.5h/day | 65% Paper II | MCQ negative marking | PDF reports | FREE NCERT links

---

## 🚀 Quick Start

### Step 1 — Install Python packages
```bash
pip install -r requirements.txt
```

### Step 2 — Configure environment
```bash
copy .env.example .env
# Now edit .env and add your BOT_TOKEN and ADMIN_CHAT_ID
```

How to get these:
- **BOT_TOKEN** → Talk to [@BotFather](https://t.me/BotFather) on Telegram → `/newbot`
- **ADMIN_CHAT_ID** → Talk to [@userinfobot](https://t.me/userinfobot) to get your chat ID

### Step 3 — Verify setup
```bash
python setup.py
```

### Step 4 — Run the bot
```bash
python bot.py
```

---

## 📁 Project Structure

```
RPSC study bot/
├── bot.py              # Main entry point — run this
├── config.py           # All settings (hours, thresholds, schedule)
├── db.py               # Database layer (aiosqlite)
├── planning.py         # Daily plan generator (65% Paper-II)
├── syllabus.py         # Syllabus formatting & book links
├── questions.py        # MCQ engine + negative marking
├── reports.py          # PDF report generator (ReportLab + matplotlib)
├── scheduler.py        # APScheduler notifications
├── setup.py            # First-run setup checker
├── requirements.txt
├── .env                # Your tokens (DO NOT SHARE)
├── .env.example
└── data/
    ├── biology_topics.csv      # Paper II syllabus
    ├── paper1_topics.csv       # Paper I GK syllabus
    ├── questions_sample.json   # MCQ question bank
    └── rpsc_bot.db             # Auto-created SQLite database
```

---

## 📋 Commands

| Command | Description |
|---------|-------------|
| `/today` | Generate today's 10.5h plan |
| `/next` | Show next pending block |
| `/done 90 8/10` | Log 90 min, score 8/10 |
| `/done 60 75%` | Log 60 min, 75% accuracy |
| `/skip` | Skip current block |
| `/mock` | Paper II mock test (15 Qs, -1/3) |
| `/mock mini` | 5-question quick mock |
| `/mock paper1` | Paper I mock |
| `/mock_history` | Recent mock scores |
| `/stats` | Today's statistics + streak |
| `/weak` | Weak topics flagged for revision |
| `/report` | Generate A4 PDF progress report |
| `/books` | FREE NCERT PDF download links |
| `/syllabus` | Full subject-wise syllabus |
| `/config` | View bot settings |

---

## ⏰ Automatic Notifications

| Time | Event |
|------|-------|
| 7:00 AM | Morning briefing + today's plan |
| 2:00 PM | Mid-day nag if < 2h logged |
| 10:00 PM | Night summary + PDF report |

---

## 📊 Daily Study Plan (10.5h)

| Block | Subject | Hours |
|-------|---------|-------|
| 🔬 Paper II — SrSec Biology | Cell Bio, Genetics, Physiology | 2.5h |
| 🧬 Paper II — Grad Biology | Mol Bio, Biotech, Ecology | 2.0h |
| 📖 Paper II — Pedagogy | Teaching methods, Bloom's | 1.0h |
| 💻 Paper II — ICT | Virtual classroom, Apps | 1.0h |
| 🏛️ Paper I — GK & Rajasthan | History, Geo, Polity | 2.0h |
| ✅ MCQ Practice | Mixed mock questions | 1.5h |
| 📝 Review & Notes | Daily consolidation | 0.5h |

---

## 🧠 Weak Topic Logic

A topic is flagged as **weak** if:
- Completion < **60%** of target hours, OR
- MCQ accuracy < **50%**

---

## 📄 PDF Reports Include
- Today's hours vs target (bar chart)
- 7-day accuracy trend (line chart)
- Weak topics analysis (horizontal bar chart)
- Mock test history table
- Recommended books & PDF links

---

## ⚙️ Tech Stack

- `aiogram==3.13.1` — Telegram Bot framework
- `aiosqlite==0.20.0` — Async SQLite
- `reportlab==4.2.2` — PDF generation
- `matplotlib==3.9.2` — Charts
- `pillow==10.4.0` — Image processing
- `apscheduler==3.10.4` — Notifications scheduler

---

*Built for RPSC School Lecturer (Biology) examination preparation.*  
*Stay consistent. 10.5h/day = Selection.* 💪
