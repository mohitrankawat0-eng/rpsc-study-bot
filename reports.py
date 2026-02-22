"""
reports.py - PDF report generation with matplotlib charts.
A4 format, tables, weak topics, progress charts.
"""
import os
import io
from datetime import date, timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from db import get_today_stats, get_weekly_stats, compute_weak_topics, get_mock_history
from config import REPORT_OUTPUT_DIR

os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)


# ── Color palette ─────────────────────────────────────────────────────────────
CLR_PRIMARY   = colors.HexColor("#1A237E")   # deep blue
CLR_ACCENT    = colors.HexColor("#0288D1")   # vivid blue
CLR_GREEN     = colors.HexColor("#2E7D32")
CLR_RED       = colors.HexColor("#C62828")
CLR_ORANGE    = colors.HexColor("#E65100")
CLR_BG        = colors.HexColor("#F5F5F5")
CLR_WHITE     = colors.white


# ────────────────────────────────────────────────────────────────────────────
# CHART GENERATORS
# ────────────────────────────────────────────────────────────────────────────
def _chart_weekly_hours(weekly: list[dict]) -> io.BytesIO:
    dates  = [w['session_date'][-5:] for w in reversed(weekly)]   # MM-DD
    hours  = [round(w['hours'] or 0, 2) for w in reversed(weekly)]
    target = [10.5] * len(dates)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(dates, hours, color="#0288D1", label="Actual", alpha=0.85, zorder=3)
    ax.plot(dates, target, "r--", linewidth=1.5, label="Target (10.5h)", zorder=4)
    ax.set_ylim(0, 14)
    ax.set_xlabel("Date", fontsize=8)
    ax.set_ylabel("Hours", fontsize=8)
    ax.set_title("Weekly Study Hours", fontsize=10, fontweight='bold')
    ax.legend(fontsize=7)
    ax.grid(axis='y', alpha=0.3, zorder=0)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_accuracy_trend(weekly: list[dict]) -> io.BytesIO:
    dates    = [w['session_date'][-5:] for w in reversed(weekly)]
    accuracy = []
    for w in reversed(weekly):
        q = w['questions'] or 0
        c = w['correct'] or 0
        accuracy.append(round(c / q * 100, 1) if q > 0 else 0)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(dates, accuracy, "o-", color="#2E7D32", linewidth=2, markersize=6)
    ax.axhline(50, color='r', linestyle='--', linewidth=1, label='50% threshold')
    ax.fill_between(dates, accuracy, 50, where=[a >= 50 for a in accuracy],
                    alpha=0.15, color='green', interpolate=True)
    ax.fill_between(dates, accuracy, 50, where=[a < 50 for a in accuracy],
                    alpha=0.15, color='red', interpolate=True)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Date", fontsize=8)
    ax.set_ylabel("Accuracy %", fontsize=8)
    ax.set_title("MCQ Accuracy Trend", fontsize=10, fontweight='bold')
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def _chart_weak_topics(weak: list[dict]) -> io.BytesIO | None:
    if not weak:
        return None
    names  = [w['name'][:25] + '…' if len(w['name']) > 25 else w['name'] for w in weak[:7]]
    compl  = [w['completion_pct'] for w in weak[:7]]
    accu   = [w['accuracy_pct'] for w in weak[:7]]

    x      = range(len(names))
    width  = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh([n - width/2 for n in x], compl, width, label='Completion %', color='#0288D1', alpha=0.85)
    ax.barh([n + width/2 for n in x], accu,  width, label='Accuracy %',   color='#E65100', alpha=0.85)
    ax.set_yticks(list(x))
    ax.set_yticklabels(names, fontsize=7)
    ax.axvline(60, color='b', linestyle=':', linewidth=1, label='60% min')
    ax.axvline(50, color='r', linestyle=':', linewidth=1, label='50% min')
    ax.set_xlim(0, 110)
    ax.set_xlabel("Percentage", fontsize=8)
    ax.set_title("Weak Topics Analysis", fontsize=10, fontweight='bold')
    ax.legend(fontsize=7, loc='lower right')
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


# ────────────────────────────────────────────────────────────────────────────
# PDF BUILDER
# ────────────────────────────────────────────────────────────────────────────
async def generate_daily_report(user_id: int, first_name: str) -> str:
    """Generate A4 PDF daily report and return file path."""
    today_str  = date.today().strftime("%d %B %Y")
    fname      = f"report_{user_id}_{date.today().isoformat()}.pdf"
    fpath      = os.path.join(REPORT_OUTPUT_DIR, fname)

    stats   = await get_today_stats(user_id)
    weekly  = await get_weekly_stats(user_id)
    weak    = await compute_weak_topics(user_id)
    mocks   = await get_mock_history(user_id, limit=3)

    doc    = SimpleDocTemplate(fpath, pagesize=A4,
                               leftMargin=2*cm, rightMargin=2*cm,
                               topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'Title', parent=styles['Title'],
        textColor=CLR_PRIMARY, fontSize=18, spaceAfter=4
    )
    h2_style = ParagraphStyle(
        'H2', parent=styles['Heading2'],
        textColor=CLR_ACCENT, fontSize=13, spaceAfter=4, spaceBefore=10
    )
    normal = styles['Normal']
    normal.fontSize = 9

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("📚 RPSC Study Bot — Daily Report", title_style))
    story.append(Paragraph(f"Student: <b>{first_name}</b> | Date: {today_str}", normal))
    story.append(HRFlowable(width="100%", thickness=2, color=CLR_PRIMARY))
    story.append(Spacer(1, 0.3*cm))

    # ── Today Stats Table ────────────────────────────────────────────────────
    story.append(Paragraph("📊 Today's Summary", h2_style))
    data = [
        ["Metric", "Value", "Target"],
        ["Hours Studied",   f"{stats['total_hours']}h", "10.5h"],
        ["Questions Done",  str(stats['total_q']),       "≥ 30"],
        ["Accuracy",        f"{stats['accuracy']}%",     "≥ 65%"],
        ["Blocks Done",     f"{stats['plan_done']}/{stats['plan_total']}", "7/7"],
    ]
    tbl = Table(data, colWidths=[6*cm, 5*cm, 5*cm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0),  CLR_PRIMARY),
        ('TEXTCOLOR',    (0, 0), (-1, 0),  CLR_WHITE),
        ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, 0),  10),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [CLR_BG, CLR_WHITE]),
        ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
        ('GRID',         (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE',     (0, 1), (-1, -1), 9),
        ('TOPPADDING',   (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.4*cm))

    # ── Weekly Charts ────────────────────────────────────────────────────────
    if weekly:
        story.append(Paragraph("📈 Weekly Progress", h2_style))
        buf_h = _chart_weekly_hours(weekly)
        buf_a = _chart_accuracy_trend(weekly)
        story.append(RLImage(buf_h, width=14*cm, height=7*cm))
        story.append(Spacer(1, 0.2*cm))
        story.append(RLImage(buf_a, width=14*cm, height=7*cm))
        story.append(Spacer(1, 0.4*cm))

    # ── Weak Topics ──────────────────────────────────────────────────────────
    if weak:
        story.append(Paragraph("🔴 Weak Topics Requiring Attention", h2_style))
        buf_w = _chart_weak_topics(weak)
        if buf_w:
            story.append(RLImage(buf_w, width=14*cm, height=7*cm))
            story.append(Spacer(1, 0.2*cm))

        wt_data = [["Topic", "Section", "Done %", "Accuracy %", "PDF Resource"]]
        for w in weak:
            wt_data.append([
                w['name'][:30],
                w['section'],
                f"{w['completion_pct']}%",
                f"{w['accuracy_pct']}%",
                w.get('free_pdf_link', '')[:40] + "…" if len(w.get('free_pdf_link', '')) > 40 else w.get('free_pdf_link', ''),
            ])
        wt_tbl = Table(wt_data, colWidths=[5.5*cm, 2.5*cm, 2*cm, 2.5*cm, 4*cm])
        wt_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0),  CLR_RED),
            ('TEXTCOLOR',    (0, 0), (-1, 0),  CLR_WHITE),
            ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#FFF3E0"), CLR_WHITE]),
            ('GRID',         (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING',   (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ]))
        story.append(wt_tbl)
        story.append(Spacer(1, 0.4*cm))
    else:
        story.append(Paragraph("✅ No weak topics — Great work!", normal))
        story.append(Spacer(1, 0.3*cm))

    # ── Mock History ─────────────────────────────────────────────────────────
    if mocks:
        story.append(Paragraph("🎯 Recent Mock Tests", h2_style))
        mk_data = [["Date", "Paper", "Score (Net)", "Accuracy", "Correct", "Wrong"]]
        for m in mocks:
            pct = round((m['score_net'] / m['total_q']) * 100, 1) if m['total_q'] > 0 else 0
            mk_data.append([
                m['mock_date'], f"Paper {m['paper']}",
                f"{m['score_net']}/{m['total_q']}", f"{pct}%",
                str(m['correct']), str(m['wrong'])
            ])
        mk_tbl = Table(mk_data, colWidths=[3*cm, 2.5*cm, 3.5*cm, 2.5*cm, 2*cm, 2*cm])
        mk_tbl.setStyle(TableStyle([
            ('BACKGROUND',   (0, 0), (-1, 0),  CLR_ACCENT),
            ('TEXTCOLOR',    (0, 0), (-1, 0),  CLR_WHITE),
            ('FONTNAME',     (0, 0), (-1, 0),  'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [CLR_BG, CLR_WHITE]),
            ('ALIGN',        (1, 0), (-1, -1), 'CENTER'),
            ('GRID',         (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING',   (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ]))
        story.append(mk_tbl)
        story.append(Spacer(1, 0.4*cm))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=CLR_ACCENT))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "🚀 <b>RPSC Study Bot</b> | antigravity_rpsc_tutor | "
        "Consistency beats talent. Keep going!",
        ParagraphStyle('footer', parent=normal, textColor=colors.grey,
                       alignment=TA_CENTER, fontSize=8)
    ))

    doc.build(story)
    return fpath


async def generate_weekly_report(user_id: int, first_name: str) -> str:
    """Alias — weekly report is a multi-day version of the daily report."""
    return await generate_daily_report(user_id, first_name)
