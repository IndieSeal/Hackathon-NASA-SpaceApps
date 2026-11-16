from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT

from schemas.contracts import SBARReport

REPORTS_DIR = Path(__file__).resolve().parent.parent / "static" / "reportes_pdf"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

ALERT_COLOR_HEX = {
    "VERDE": "#10b981",
    "AMARILLO": "#f59e0b",
    "ROJO": "#ef4444",
}


def report_filename(sbar_report: SBARReport) -> str:
    timestamp_int = int(sbar_report.generated_at)
    return f"SBAR_{sbar_report.astronaut_id}_{timestamp_int}.pdf"


def write_pdf_report(sbar_report: SBARReport) -> str:
    filename = report_filename(sbar_report)
    filepath = REPORTS_DIR / filename

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SbarTitle", parent=styles["Title"], alignment=TA_LEFT, fontSize=16, spaceAfter=4
    )
    meta_style = ParagraphStyle(
        "SbarMeta", parent=styles["Normal"], fontSize=9, textColor=HexColor("#475569")
    )
    body_style = ParagraphStyle(
        "SbarBody", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=6
    )

    alert_hex = ALERT_COLOR_HEX.get(sbar_report.alert_color, "#475569")

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=filename,
    )

    story = [
        Paragraph("REPORTE MEDICO SBAR - AEROSPACE HEALTH MONITORING", title_style),
        Spacer(1, 4),
        Table(
            [[f"ASTRONAUTA: {sbar_report.astronaut_id}", f"ALERTA: {sbar_report.alert_color}"]],
            colWidths=[8 * cm, 8 * cm],
            style=TableStyle(
                [
                    ("TEXTCOLOR", (1, 0), (1, 0), HexColor(alert_hex)),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                ]
            ),
        ),
        Spacer(1, 6),
        Paragraph(
            f"Diagnostico: {sbar_report.diagnosis} | "
            f"Tiempo de inferencia: {sbar_report.inference_time_sec:.2f} s | "
            f"Generado: {sbar_report.generated_at:.0f} (UNIX)",
            meta_style,
        ),
        Spacer(1, 14),
    ]

    for paragraph in sbar_report.report_text.split("\n\n"):
        clean = paragraph.strip()
        if not clean:
            continue
        escaped = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        story.append(Paragraph(escaped, body_style))

    doc.build(story)
    return filename
