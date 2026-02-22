"""
setup.py - First-run environment checker and database initialiser.
Run this before bot.py if you want to verify your setup.
"""
import asyncio
import os
import sys

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def check_env() -> bool:
    ok = True
    token = os.getenv("BOT_TOKEN", "")
    admin = os.getenv("ADMIN_CHAT_ID", "0")

    print("\n[*] Checking environment...")
    if not token or token == "your_telegram_bot_token_here":
        print("  [FAIL] BOT_TOKEN not set in .env")
        ok = False
    else:
        print(f"  [OK] BOT_TOKEN found ({token[:8]}...)")

    if admin == "0":
        print("  [WARN] ADMIN_CHAT_ID not set - notifications will be disabled")
    else:
        print(f"  [OK] ADMIN_CHAT_ID: {admin}")

    return ok


def check_data_files() -> bool:
    ok = True
    files = [
        "data/biology_topics.csv",
        "data/paper1_topics.csv",
        "data/questions_sample.json",
    ]
    print("\n[*] Checking data files...")
    for f in files:
        if os.path.exists(f):
            print(f"  [OK] {f}")
        else:
            print(f"  [FAIL] {f} MISSING")
            ok = False
    return ok


async def init_database() -> None:
    from db import init_db
    print("\n[*] Initialising database...")
    await init_db()


def check_packages() -> bool:
    ok = True
    required = [
        ("aiogram",     "aiogram"),
        ("aiosqlite",   "aiosqlite"),
        ("reportlab",   "reportlab"),
        ("matplotlib",  "matplotlib"),
        ("PIL",         "Pillow"),
        ("apscheduler", "apscheduler"),
        ("dotenv",      "python-dotenv"),
        ("pandas",      "pandas"),
    ]
    print("\n[*] Checking packages...")
    for imp, pkg in required:
        try:
            __import__(imp)
            print(f"  [OK] {pkg}")
        except ImportError:
            print(f"  [FAIL] {pkg} not installed -- run: pip install {pkg}")
            ok = False
    return ok


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    print("=" * 50)
    print("  RPSC Study Bot -- Setup Checker")
    print("=" * 50)

    all_ok = True
    all_ok &= check_packages()
    all_ok &= check_env()
    all_ok &= check_data_files()

    os.makedirs("data",    exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    asyncio.run(init_database())

    print("\n" + "=" * 50)
    if all_ok:
        print("[SUCCESS] All checks passed! Run: python bot.py")
    else:
        print("[WARNING] Fix the issues above, then run: python bot.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
