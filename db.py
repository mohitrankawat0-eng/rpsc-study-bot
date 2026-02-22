"""
db.py - Database layer for RPSC Study Bot (aiosqlite)
Auto-creates all tables and loads CSV/JSON data on first run.
Includes adaptive intelligence tables: user_profiles, daily_calibration.
"""
import json
import csv
import os
import aiosqlite
from datetime import date, datetime
from config import DB_PATH, BIOLOGY_CSV, PAPER1_CSV, QUESTIONS_JSON

# ────────────────────────────────────────────────────────────────────────────
# SCHEMA
# ────────────────────────────────────────────────────────────────────────────
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_name  TEXT,
    exam_date   TEXT    DEFAULT '2025-12-01',
    daily_goal  REAL    DEFAULT 10.5,
    onboarded   INTEGER DEFAULT 0,
    created_at  TEXT    DEFAULT (datetime('now','localtime'))
);

-- ── ADAPTIVE INTELLIGENCE TABLES ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id                 INTEGER PRIMARY KEY,
    baseline_paper1_score   REAL    DEFAULT 0,
    baseline_paper2_score   REAL    DEFAULT 0,
    topic_accuracy          TEXT    DEFAULT '{}',
    avg_response_time       REAL    DEFAULT 45,
    skip_rate               REAL    DEFAULT 0,
    error_type              TEXT    DEFAULT 'conceptual',
    recommended_daily_hours REAL    DEFAULT 10.5,
    recommended_block_len   INTEGER DEFAULT 90,
    learning_style          TEXT    DEFAULT 'Theory->MCQ',
    diagnostic_done         INTEGER DEFAULT 0,
    last_calibrated         TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS daily_calibration (
    cal_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    cal_date        TEXT    NOT NULL,
    accuracy        REAL    DEFAULT 0,
    completion_rate REAL    DEFAULT 0,
    actual_hours    REAL    DEFAULT 0,
    fatigue_score   REAL    DEFAULT 0,
    questions_done  INTEGER DEFAULT 0,
    correct         INTEGER DEFAULT 0,
    UNIQUE(user_id, cal_date),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- ── CORE TABLES ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS topics (
    topic_id        INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    paper           INTEGER NOT NULL,
    section         TEXT NOT NULL,
    target_hours    REAL    DEFAULT 0,
    marks_weight    INTEGER DEFAULT 0,
    priority        TEXT    DEFAULT 'MEDIUM',
    pyq_weight      INTEGER DEFAULT 0,
    recommended_books TEXT,
    free_pdf_link   TEXT
);

CREATE TABLE IF NOT EXISTS daily_plan (
    plan_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    plan_date   TEXT    NOT NULL,
    block_index INTEGER NOT NULL,
    topic_id    INTEGER,
    label       TEXT,
    section     TEXT,
    paper       INTEGER,
    hours       REAL,
    emoji       TEXT,
    status      TEXT    DEFAULT 'pending',
    FOREIGN KEY (user_id)  REFERENCES users(user_id),
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    topic_id        INTEGER,
    session_date    TEXT    NOT NULL,
    hours_studied   REAL    DEFAULT 0,
    questions_done  INTEGER DEFAULT 0,
    correct_answers INTEGER DEFAULT 0,
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id)  REFERENCES users(user_id),
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
);

CREATE TABLE IF NOT EXISTS mocks (
    mock_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    mock_date   TEXT    NOT NULL,
    paper       INTEGER,
    total_q     INTEGER DEFAULT 0,
    attempted   INTEGER DEFAULT 0,
    correct     INTEGER DEFAULT 0,
    wrong       INTEGER DEFAULT 0,
    score_raw   REAL    DEFAULT 0,
    score_net   REAL    DEFAULT 0,
    time_taken  INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS streaks (
    streak_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    streak_date TEXT    NOT NULL,
    hours_done  REAL    DEFAULT 0,
    is_complete INTEGER DEFAULT 0,
    UNIQUE(user_id, streak_date),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS weak_topics (
    wt_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    topic_id        INTEGER NOT NULL,
    completion_pct  REAL DEFAULT 0,
    accuracy_pct    REAL DEFAULT 0,
    flagged_on      TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(user_id, topic_id),
    FOREIGN KEY (user_id)  REFERENCES users(user_id),
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
);

CREATE TABLE IF NOT EXISTS questions (
    q_id        INTEGER PRIMARY KEY,
    paper       INTEGER,
    section     TEXT,
    topic_id    INTEGER,
    question    TEXT,
    opt_a       TEXT,
    opt_b       TEXT,
    opt_c       TEXT,
    opt_d       TEXT,
    answer_idx  INTEGER,
    level       TEXT,
    explanation TEXT,
    is_diagnostic INTEGER DEFAULT 0,
    FOREIGN KEY (topic_id) REFERENCES topics(topic_id)
);
"""

# ────────────────────────────────────────────────────────────────────────────
# INIT
# ────────────────────────────────────────────────────────────────────────────
async def init_db() -> None:
    """Create schema and load seed data (idempotent)."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
        await _seed_topics(db)
        await _seed_questions(db)
        await db.commit()
    print("[OK] Database initialised at", DB_PATH)


async def _seed_topics(db: aiosqlite.Connection) -> None:
    cur = await db.execute("SELECT COUNT(*) FROM topics")
    count = (await cur.fetchone())[0]
    if count > 0:
        return

    rows_bio = []
    if os.path.exists(BIOLOGY_CSV):
        with open(BIOLOGY_CSV, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rows_bio.append((
                    int(row['topic_id']), row['name'], int(row['paper']),
                    row['section'], float(row['target_hours']),
                    int(row['marks_weight']), row['priority'],
                    int(row.get('pyq_weight', 0)),
                    row.get('recommended_books', ''), row.get('free_pdf_link', '')
                ))

    rows_p1 = []
    if os.path.exists(PAPER1_CSV):
        with open(PAPER1_CSV, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rows_p1.append((
                    int(row['topic_id']) + 100, row['name'], int(row['paper']),
                    row['section'], float(row['target_hours']),
                    int(row['marks_weight']), row['priority'],
                    0,
                    row.get('recommended_books', ''), row.get('free_pdf_link', '')
                ))

    all_rows = rows_bio + rows_p1
    await db.executemany(
        """INSERT OR IGNORE INTO topics
           (topic_id,name,paper,section,target_hours,marks_weight,priority,
            pyq_weight,recommended_books,free_pdf_link)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        all_rows
    )
    print(f"  [DB] Seeded {len(all_rows)} topics.")


async def _seed_questions(db: aiosqlite.Connection) -> None:
    cur = await db.execute("SELECT COUNT(*) FROM questions")
    count = (await cur.fetchone())[0]
    if count > 0:
        return

    if not os.path.exists(QUESTIONS_JSON):
        return

    with open(QUESTIONS_JSON, encoding='utf-8') as f:
        questions = json.load(f)

    rows = []
    for q in questions:
        opts = q.get('options', ['', '', '', ''])
        rows.append((
            q['id'], q.get('paper', 2), q.get('section', ''),
            q.get('topic_id', 1), q['question'],
            opts[0] if len(opts) > 0 else '',
            opts[1] if len(opts) > 1 else '',
            opts[2] if len(opts) > 2 else '',
            opts[3] if len(opts) > 3 else '',
            q.get('answer_index', 0), q.get('level', 'medium'),
            q.get('explanation', ''),
            1 if q.get('diagnostic') else 0
        ))

    await db.executemany(
        """INSERT OR IGNORE INTO questions
           (q_id,paper,section,topic_id,question,opt_a,opt_b,opt_c,opt_d,
            answer_idx,level,explanation,is_diagnostic)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows
    )
    print(f"  [DB] Seeded {len(rows)} questions.")


# ────────────────────────────────────────────────────────────────────────────
# USER HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def get_or_create_user(user_id: int, username: str, first_name: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """INSERT OR IGNORE INTO users (user_id, username, first_name)
               VALUES (?, ?, ?)""",
            (user_id, username, first_name)
        )
        await db.execute(
            """INSERT OR IGNORE INTO user_profiles (user_id) VALUES (?)""",
            (user_id,)
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return dict(await cur.fetchone())


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_user_onboarded(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET onboarded=1 WHERE user_id=?", (user_id,))
        await db.commit()


async def is_onboarded(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT onboarded FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row[0]) if row else False


# ────────────────────────────────────────────────────────────────────────────
# USER PROFILE (ADAPTIVE)
# ────────────────────────────────────────────────────────────────────────────
async def get_user_profile(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM user_profiles WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        if not row:
            return None
        profile = dict(row)
        # Parse JSON field
        try:
            profile['topic_accuracy'] = json.loads(profile['topic_accuracy'] or '{}')
        except Exception:
            profile['topic_accuracy'] = {}
        return profile


async def save_diagnostic_results(
        user_id: int,
        p1_score: float,
        p2_score: float,
        topic_accuracy: dict,
        avg_response_time: float,
        skip_rate: float,
) -> dict:
    """
    Compute learning profile and recommended hours/block length, then save.
    Returns the computed recommendations.
    """
    # Determine error type: conceptual (low accuracy on medium/hard) vs careless
    error_type = "conceptual" if p2_score < 0.5 else "careless"

    # Recommended block length based on avg response time
    if avg_response_time < 30:
        block_len = 60    # Fast responder → shorter blocks
    elif avg_response_time < 60:
        block_len = 90    # Normal
    else:
        block_len = 120   # Slow/careful → longer blocks

    # Recommended daily hours
    if p2_score < 0.4 or p1_score < 0.4:
        daily_hours = 11.0   # Poor baseline → intensive
    elif p2_score > 0.7 and p1_score > 0.7:
        daily_hours = 10.0   # Strong baseline → standard
    else:
        daily_hours = 10.5

    learning_style = "Theory→MCQ" if error_type == "conceptual" else "MCQ→Theory"

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_profiles
               (user_id, baseline_paper1_score, baseline_paper2_score,
                topic_accuracy, avg_response_time, skip_rate, error_type,
                recommended_daily_hours, recommended_block_len,
                learning_style, diagnostic_done, last_calibrated)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,date('now','localtime'))
               ON CONFLICT(user_id) DO UPDATE SET
               baseline_paper1_score=excluded.baseline_paper1_score,
               baseline_paper2_score=excluded.baseline_paper2_score,
               topic_accuracy=excluded.topic_accuracy,
               avg_response_time=excluded.avg_response_time,
               skip_rate=excluded.skip_rate,
               error_type=excluded.error_type,
               recommended_daily_hours=excluded.recommended_daily_hours,
               recommended_block_len=excluded.recommended_block_len,
               learning_style=excluded.learning_style,
               diagnostic_done=1,
               last_calibrated=date('now','localtime')""",
            (user_id, p1_score, p2_score,
             json.dumps(topic_accuracy), avg_response_time,
             skip_rate, error_type, daily_hours, block_len,
             learning_style)
        )
        # Also update user's daily_goal
        await db.execute(
            "UPDATE users SET daily_goal=? WHERE user_id=?",
            (daily_hours, user_id)
        )
        await db.commit()

    return {
        "daily_hours":    daily_hours,
        "block_len":      block_len,
        "error_type":     error_type,
        "learning_style": learning_style,
    }


async def update_topic_accuracy(user_id: int, section: str, accuracy: float) -> None:
    """Update a single topic accuracy in the JSON profile."""
    profile = await get_user_profile(user_id)
    if not profile:
        return
    ta = profile.get('topic_accuracy', {})
    ta[section] = round(accuracy, 2)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_profiles SET topic_accuracy=? WHERE user_id=?",
            (json.dumps(ta), user_id)
        )
        await db.commit()


async def save_calibration(user_id: int, accuracy: float, completion_rate: float,
                           actual_hours: float, questions_done: int, correct: int) -> dict:
    """
    Save nightly 5Q calibration and auto-adjust next-day plan.
    Returns adjustment message.
    """
    today = date.today().isoformat()
    # Fatigue score: high if low accuracy despite many hours
    fatigue = max(0.0, min(1.0, (actual_hours / 10.5) - accuracy))

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO daily_calibration
               (user_id, cal_date, accuracy, completion_rate, actual_hours,
                fatigue_score, questions_done, correct)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id, cal_date) DO UPDATE SET
               accuracy=excluded.accuracy,
               completion_rate=excluded.completion_rate,
               actual_hours=excluded.actual_hours,
               fatigue_score=excluded.fatigue_score""",
            (user_id, today, accuracy, completion_rate, actual_hours,
             fatigue, questions_done, correct)
        )

        # Get last 3 days to detect burnout / improvement
        cur = await db.execute(
            """SELECT accuracy, completion_rate, actual_hours FROM daily_calibration
               WHERE user_id=? ORDER BY cal_date DESC LIMIT 3""",
            (user_id,)
        )
        rows = await cur.fetchall()

        # Fetch current recommended hours
        cur2 = await db.execute(
            "SELECT recommended_daily_hours FROM user_profiles WHERE user_id=?",
            (user_id,)
        )
        prow = await cur2.fetchone()
        current_hours = prow[0] if prow else 10.5

        adjustment_msg = ""
        new_hours = current_hours

        if len(rows) >= 1:
            if completion_rate < 0.70:
                new_hours = max(8.0, current_hours - 1.0)
                adjustment_msg = f"⬇️ Target reduced to {new_hours}h (completion < 70%)"
            elif len(rows) >= 2:
                # Check improvement
                prev_acc  = rows[1][0] if len(rows) > 1 else accuracy
                improvement = accuracy - prev_acc
                if improvement > 0.15:
                    new_hours = min(12.0, current_hours + 0.5)
                    adjustment_msg = f"⬆️ Target raised to {new_hours}h (+15% improvement!)"

        # Burnout detection: 3+ consecutive days with completion < 0.5
        if len(rows) >= 3 and all(r[1] < 0.5 for r in rows[:3]):
            new_hours = max(8.0, current_hours * 0.7)
            adjustment_msg = f"🔥 Burnout detected! Reduced to {new_hours:.1f}h tomorrow."

        if new_hours != current_hours:
            await db.execute(
                "UPDATE user_profiles SET recommended_daily_hours=? WHERE user_id=?",
                (new_hours, user_id)
            )
            await db.execute(
                "UPDATE users SET daily_goal=? WHERE user_id=?",
                (new_hours, user_id)
            )

        await db.commit()

    return {"new_hours": new_hours, "adjustment_msg": adjustment_msg}


async def get_calibration_history(user_id: int, days: int = 7) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM daily_calibration WHERE user_id=?
               ORDER BY cal_date DESC LIMIT ?""",
            (user_id, days)
        )
        return [dict(r) for r in await cur.fetchall()]


# ────────────────────────────────────────────────────────────────────────────
# DAILY PLAN HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def get_today_plan(user_id: int) -> list[dict]:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT dp.*, t.name as topic_name, t.free_pdf_link, t.recommended_books
               FROM daily_plan dp
               LEFT JOIN topics t ON dp.topic_id = t.topic_id
               WHERE dp.user_id=? AND dp.plan_date=?
               ORDER BY dp.block_index""",
            (user_id, today)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def save_daily_plan(user_id: int, blocks: list[dict]) -> None:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM daily_plan WHERE user_id=? AND plan_date=?",
            (user_id, today)
        )
        for i, b in enumerate(blocks):
            await db.execute(
                """INSERT INTO daily_plan
                   (user_id,plan_date,block_index,topic_id,label,section,paper,hours,emoji,status)
                   VALUES (?,?,?,?,?,?,?,?,?,'pending')""",
                (user_id, today, i,
                 b.get('topic_id'), b.get('label'), b.get('section'),
                 b.get('paper'), b.get('hours'), b.get('emoji'))
            )
        await db.commit()


async def mark_block_done(user_id: int, block_index: int) -> bool:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE daily_plan SET status='done'
               WHERE user_id=? AND plan_date=? AND block_index=?""",
            (user_id, today, block_index)
        )
        await db.commit()
        return cur.rowcount > 0


async def mark_block_skipped(user_id: int, block_index: int) -> bool:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """UPDATE daily_plan SET status='skipped'
               WHERE user_id=? AND plan_date=? AND block_index=?""",
            (user_id, today, block_index)
        )
        await db.commit()
        return cur.rowcount > 0


# ────────────────────────────────────────────────────────────────────────────
# SESSION HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def log_session(user_id: int, topic_id: int | None,
                      hours: float, q_done: int, correct: int,
                      notes: str = "") -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO sessions
               (user_id,topic_id,session_date,hours_studied,questions_done,correct_answers,notes)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, topic_id, today, hours, q_done, correct, notes)
        )
        await db.commit()
        return cur.lastrowid


async def get_today_stats(user_id: int) -> dict:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COALESCE(SUM(hours_studied),0),
                      COALESCE(SUM(questions_done),0),
                      COALESCE(SUM(correct_answers),0)
               FROM sessions WHERE user_id=? AND session_date=?""",
            (user_id, today)
        )
        row    = await cur.fetchone()
        p_cur  = await db.execute(
            """SELECT COUNT(*), SUM(CASE WHEN status='done' THEN 1 ELSE 0 END)
               FROM daily_plan WHERE user_id=? AND plan_date=?""",
            (user_id, today)
        )
        p_row  = await p_cur.fetchone()
        hours, total_q, correct = row
        plan_total = p_row[0] or 0
        plan_done  = p_row[1] or 0
        accuracy   = (correct / total_q * 100) if total_q > 0 else 0
        return {
            "total_hours":   round(float(hours), 2),
            "total_q":       int(total_q),
            "total_correct": int(correct),
            "accuracy":      round(accuracy, 1),
            "plan_total":    plan_total,
            "plan_done":     plan_done,
        }


async def get_weekly_stats(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT session_date,
                      SUM(hours_studied) as hours,
                      SUM(questions_done) as questions,
                      SUM(correct_answers) as correct
               FROM sessions WHERE user_id=?
               GROUP BY session_date
               ORDER BY session_date DESC LIMIT 7""",
            (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]


# ────────────────────────────────────────────────────────────────────────────
# MOCK HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def save_mock(user_id: int, paper: int, total_q: int,
                    attempted: int, correct: int, wrong: int,
                    time_taken: int) -> dict:
    from config import NEGATIVE_MARKING_RATIO
    score_raw = correct
    score_net = correct - (wrong * NEGATIVE_MARKING_RATIO)
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO mocks
               (user_id,mock_date,paper,total_q,attempted,correct,wrong,
                score_raw,score_net,time_taken)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, today, paper, total_q, attempted, correct, wrong,
             score_raw, score_net, time_taken)
        )
        await db.commit()
    return {"score_raw": score_raw, "score_net": round(score_net, 2)}


async def get_mock_history(user_id: int, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM mocks WHERE user_id=?
               ORDER BY mock_date DESC LIMIT ?""",
            (user_id, limit)
        )
        return [dict(r) for r in await cur.fetchall()]


# ────────────────────────────────────────────────────────────────────────────
# STREAK HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def update_streak(user_id: int, hours_done: float) -> int:
    from config import STREAK_GOAL_HOURS
    today = date.today().isoformat()
    is_complete = 1 if hours_done >= STREAK_GOAL_HOURS else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO streaks (user_id, streak_date, hours_done, is_complete)
               VALUES (?,?,?,?)
               ON CONFLICT(user_id, streak_date) DO UPDATE SET
               hours_done=excluded.hours_done,
               is_complete=excluded.is_complete""",
            (user_id, today, hours_done, is_complete)
        )
        await db.commit()
        cur = await db.execute(
            """SELECT COUNT(*) FROM streaks
               WHERE user_id=? AND is_complete=1
               AND streak_date >= date('now','-30 days')""",
            (user_id,)
        )
        return (await cur.fetchone())[0]


async def get_streak(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """SELECT COUNT(*) FROM streaks
               WHERE user_id=? AND is_complete=1
               AND streak_date >= date('now','-30 days')""",
            (user_id,)
        )
        return (await cur.fetchone())[0] or 0


# ────────────────────────────────────────────────────────────────────────────
# TOPIC & WEAK TOPIC HELPERS
# ────────────────────────────────────────────────────────────────────────────
async def get_all_topics(paper: int | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if paper:
            cur = await db.execute(
                "SELECT * FROM topics WHERE paper=? ORDER BY priority DESC, marks_weight DESC",
                (paper,)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM topics ORDER BY paper, priority DESC"
            )
        return [dict(r) for r in await cur.fetchall()]


async def get_topic(topic_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM topics WHERE topic_id=?", (topic_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def compute_weak_topics(user_id: int) -> list[dict]:
    from config import WEAK_COMPLETION_THRESHOLD, WEAK_ACCURACY_THRESHOLD
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT s.topic_id, t.name, t.section, t.target_hours,
                      t.free_pdf_link, t.recommended_books,
                      SUM(s.hours_studied) as studied,
                      SUM(s.questions_done) as q_done,
                      SUM(s.correct_answers) as correct
               FROM sessions s
               JOIN topics t ON s.topic_id = t.topic_id
               WHERE s.user_id=?
               GROUP BY s.topic_id""",
            (user_id,)
        )
        rows = await cur.fetchall()
        weak = []
        for r in rows:
            r = dict(r)
            completion = (r['studied'] / r['target_hours']) if r['target_hours'] > 0 else 0
            accuracy   = (r['correct'] / r['q_done']) if r['q_done'] > 0 else 0
            if completion < WEAK_COMPLETION_THRESHOLD or accuracy < WEAK_ACCURACY_THRESHOLD:
                r['completion_pct'] = round(completion * 100, 1)
                r['accuracy_pct']   = round(accuracy * 100, 1)
                weak.append(r)
        return weak


async def get_questions(section: str | None = None,
                        topic_id: int | None = None,
                        limit: int = 10,
                        diagnostic_only: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if diagnostic_only:
            cur = await db.execute(
                "SELECT * FROM questions WHERE is_diagnostic=1 ORDER BY RANDOM() LIMIT ?",
                (limit,)
            )
        elif topic_id:
            cur = await db.execute(
                "SELECT * FROM questions WHERE topic_id=? AND is_diagnostic=0 ORDER BY RANDOM() LIMIT ?",
                (topic_id, limit)
            )
        elif section:
            cur = await db.execute(
                "SELECT * FROM questions WHERE section=? AND is_diagnostic=0 ORDER BY RANDOM() LIMIT ?",
                (section, limit)
            )
        else:
            cur = await db.execute(
                "SELECT * FROM questions WHERE is_diagnostic=0 ORDER BY RANDOM() LIMIT ?",
                (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]


async def get_diagnostic_questions() -> list[dict]:
    """Return exactly the 30 diagnostic questions in fixed order:
    10 Paper I, 15 Paper II, 5 Mental Ability."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        result = []
        for section, limit in [("History", 3), ("Geography", 3), ("Polity", 2),
                                 ("SrSec", 5), ("Grad", 5), ("Pedagogy", 3),
                                 ("MentalAbility", 5)]:
            cur = await db.execute(
                """SELECT * FROM questions
                   WHERE is_diagnostic=1 AND section=?
                   ORDER BY q_id LIMIT ?""",
                (section, limit)
            )
            rows = await cur.fetchall()
            result.extend([dict(r) for r in rows])
        # Fill up remaining Paper I history if needed
        if len(result) < 25:
            cur = await db.execute(
                """SELECT * FROM questions WHERE is_diagnostic=1
                   ORDER BY RANDOM() LIMIT ?""",
                (30,)
            )
            result = [dict(r) for r in await cur.fetchall()]
        return result[:30]
