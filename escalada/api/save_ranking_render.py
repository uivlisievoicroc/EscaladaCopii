"""Rendering helpers for ranking exports."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEFAULT_FONT = "Helvetica"
try:
    font_paths = [
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\DejaVuSans.ttf",
        "/Library/Fonts/DejaVuSans.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            pdfmetrics.registerFont(TTFont("DejaVuSans", path))
            DEFAULT_FONT = "DejaVuSans"
            break
except Exception:
    import logging

    logging.warning(
        "Could not register DejaVuSans font. Using Helvetica (limited diacritics support)."
    )
    DEFAULT_FONT = "Helvetica"


def df_to_pdf(df: pd.DataFrame, pdf_path: Path, title: str = "Ranking") -> None:
    """Render a DataFrame as a simple landscape-A4 PDF table."""
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        alignment=1,
        fontSize=18,
        fontName=DEFAULT_FONT,
        spaceAfter=12,
    )

    data = [df.columns.tolist()] + df.astype(str).values.tolist()
    table = Table(data, hAlign="CENTER")
    tbl_style = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), DEFAULT_FONT),
            ("FONTNAME", (0, 1), (-1, -1), DEFAULT_FONT),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ]
    )
    for i in range(1, len(data)):
        bg_color = colors.whitesmoke if i % 2 == 0 else colors.lightgrey
        tbl_style.add("BACKGROUND", (0, i), (-1, i), bg_color)

    table.setStyle(tbl_style)

    elements = [Paragraph(title, title_style), Spacer(1, 12), table]
    doc.build(elements)
