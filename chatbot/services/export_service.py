import io
import re
from datetime import datetime

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer,
        HRFlowable, Table, TableStyle, KeepTogether
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ── Inline markdown → ReportLab HTML ─────────────────────────────────────────

def _md_inline(text: str) -> str:
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'\*\*\*(.*?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'\*\*(.*?)\*\*',     r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*',         r'<i>\1</i>', text)
    text = re.sub(r'`(.*?)`',           r'<font name="Courier" color="#1a6bcc">\1</font>', text)
    return text


def _is_table_separator(line: str) -> bool:
    return bool(re.match(r'^\|[\s\-:|]+\|', line.strip()))


def _parse_table(table_lines: list) -> list:
    """Parse markdown table lines → list of rows (list of strings)."""
    rows = []
    for line in table_lines:
        if _is_table_separator(line):
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        rows.append(cells)
    return rows


def _build_rl_table(rows: list) -> Table:
    """Convert parsed rows to a styled ReportLab Table."""
    brand = colors.HexColor('#1a3a5c')
    light = colors.HexColor('#f0f4f8')
    grid  = colors.HexColor('#c8d0d8')

    data = []
    for r, cells in enumerate(rows):
        rendered = [Paragraph(_md_inline(c), ParagraphStyle(
            'TC',
            fontName='Helvetica-Bold' if r == 0 else 'Helvetica',
            fontSize=8,
            textColor=colors.white if r == 0 else colors.HexColor('#1e293b'),
            leading=11,
        )) for c in cells]
        data.append(rendered)

    col_count = max(len(r) for r in data) if data else 1
    col_width  = (A4[0] - 4 * cm) / col_count

    t = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    style = [
        ('BACKGROUND',  (0, 0), (-1, 0),  brand),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light]),
        ('GRID',        (0, 0), (-1, -1),  0.4, grid),
        ('VALIGN',      (0, 0), (-1, -1),  'MIDDLE'),
        ('TOPPADDING',  (0, 0), (-1, -1),  5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1),  6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(style))
    return t


# ── Markdown → ReportLab elements ────────────────────────────────────────────

def _md_to_elements(text: str, base_styles: dict) -> list:
    """Convert a full markdown string to a list of ReportLab flowables."""
    elements = []
    lines    = text.split('\n')
    i        = 0

    s_h1     = base_styles['h1']
    s_h2     = base_styles['h2']
    s_h3     = base_styles['h3']
    s_body   = base_styles['body']
    s_bullet = base_styles['bullet']
    s_sub    = base_styles['sub']
    s_code   = base_styles['code']

    while i < len(lines):
        line = lines[i]

        # ── Table detection
        if '|' in line:
            table_block = []
            while i < len(lines) and '|' in lines[i]:
                table_block.append(lines[i])
                i += 1
            rows = _parse_table(table_block)
            if rows:
                elements.append(Spacer(1, 4))
                elements.append(_build_rl_table(rows))
                elements.append(Spacer(1, 6))
            continue

        # ── Code block
        if line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            if code_lines:
                elements.append(Paragraph('\n'.join(code_lines), s_code))
            i += 1
            continue

        # ── Horizontal rule
        if re.match(r'^[-*_]{3,}$', line.strip()):
            elements.append(HRFlowable(width='100%', thickness=0.5,
                                       color=colors.HexColor('#d0d7de'), spaceAfter=4))
            i += 1
            continue

        # ── Headers
        if line.startswith('#### '):
            elements.append(Paragraph(_md_inline(line[5:]), s_h3))
        elif line.startswith('### '):
            elements.append(Paragraph(_md_inline(line[4:]), s_h3))
        elif line.startswith('## '):
            elements.append(Paragraph(_md_inline(line[3:]), s_h2))
        elif line.startswith('# '):
            elements.append(Paragraph(_md_inline(line[2:]), s_h1))

        # ── Sub-bullet (2 or 4 spaces / tab)
        elif re.match(r'^(\s{2,}|\t)[•\-\*◦○]', line):
            content = re.sub(r'^(\s+)[•\-\*◦○]\s*', '', line)
            elements.append(Paragraph(f'◦ {_md_inline(content)}', s_sub))

        # ── Bullet
        elif re.match(r'^[•\-\*]\s', line):
            content = re.sub(r'^[•\-\*]\s', '', line)
            elements.append(Paragraph(f'• {_md_inline(content)}', s_bullet))

        # ── Numbered list
        elif re.match(r'^\d+\.\s', line):
            content = re.sub(r'^\d+\.\s', '', line)
            elements.append(Paragraph(_md_inline(content), s_bullet))

        # ── Empty line
        elif line.strip() == '':
            elements.append(Spacer(1, 3))

        # ── Normal paragraph
        else:
            if line.strip():
                elements.append(Paragraph(_md_inline(line), s_body))

        i += 1

    return elements


# ── Export service ────────────────────────────────────────────────────────────

class ExportService:

    # ── Markdown export ───────────────────────────────────────────────────────

    def export_markdown(self, conversation) -> str:
        lines = [
            f"# {conversation.title}",
            "",
            f"- **Date :** {conversation.created_at.strftime('%d/%m/%Y %H:%M')}",
            f"- **Utilisateur :** {conversation.user.get_full_name()}",
            f"- **Filiale :** {conversation.user.filiale}",
            "",
            "---",
            "",
        ]
        for msg in conversation.messages.all():
            ts = msg.created_at.strftime('%H:%M')
            if msg.role == 'user':
                lines += [f"## Vous ({ts})", "", msg.content, "", "---", ""]
            else:
                lines += [f"## LabAssistant ({ts})", "", msg.content, "", "---", ""]
        lines.append(
            f"*Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')} "
            f"— LabAssistant · Poulina Group Holding*"
        )
        return "\n".join(lines)

    # ── PDF export ────────────────────────────────────────────────────────────

    def export_pdf(self, conversation) -> io.BytesIO:
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab n'est pas installé. Exécutez: pip install reportlab")

        buffer = io.BytesIO()
        brand  = colors.HexColor('#1a3a5c')

        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm,
            title=conversation.title,
            author="LabAssistant — Poulina Group Holding",
        )

        # ── Styles
        base = getSampleStyleSheet()

        def ps(name, **kw):
            return ParagraphStyle(name, parent=base['Normal'], **kw)

        styles = {
            'h1': ps('H1', fontName='Helvetica-Bold', fontSize=14,
                     textColor=brand, spaceBefore=10, spaceAfter=4),
            'h2': ps('H2', fontName='Helvetica-Bold', fontSize=12,
                     textColor=brand, spaceBefore=8, spaceAfter=3),
            'h3': ps('H3', fontName='Helvetica-Bold', fontSize=10,
                     textColor=colors.HexColor('#2d5986'), spaceBefore=6, spaceAfter=2),
            'body': ps('Body', fontSize=9, leading=13, spaceAfter=3,
                       textColor=colors.HexColor('#1e293b')),
            'bullet': ps('Bullet', fontSize=9, leading=13, leftIndent=12,
                         spaceAfter=2, textColor=colors.HexColor('#1e293b')),
            'sub': ps('Sub', fontSize=8, leading=12, leftIndent=24,
                      spaceAfter=2, textColor=colors.HexColor('#475569')),
            'code': ps('Code', fontName='Courier', fontSize=7.5,
                       backColor=colors.HexColor('#f1f5f9'), leading=11,
                       leftIndent=8, rightIndent=8, spaceAfter=4),
        }

        title_style = ps('Title', fontName='Helvetica-Bold', fontSize=18,
                         textColor=brand, spaceAfter=4, spaceBefore=0)
        meta_style  = ps('Meta', fontSize=8, textColor=colors.grey, spaceAfter=10)
        label_style = ps('Label', fontSize=7.5, textColor=colors.HexColor('#6e7681'),
                         spaceAfter=2, spaceBefore=8)
        user_bg_style = ps('UserBg', fontSize=9, leading=13,
                           textColor=colors.HexColor('#0d3163'),
                           backColor=colors.HexColor('#dbeafe'),
                           leftIndent=8, rightIndent=8, spaceBefore=2, spaceAfter=4)
        footer_style  = ps('Footer', fontSize=7.5, textColor=colors.grey,
                            alignment=TA_CENTER)

        # ── Document header
        elements = [
            Paragraph(f"LabAssistant — {conversation.title}", title_style),
            Paragraph(
                f"Utilisateur : {conversation.user.get_full_name()} &nbsp;·&nbsp; "
                f"Filiale : {conversation.user.filiale} &nbsp;·&nbsp; "
                f"Date : {conversation.created_at.strftime('%d/%m/%Y %H:%M')}",
                meta_style
            ),
            HRFlowable(width='100%', thickness=2, color=brand, spaceAfter=10),
        ]

        # ── Messages
        for msg in conversation.messages.all():
            ts = msg.created_at.strftime('%H:%M')

            if msg.role == 'user':
                block = [
                    Paragraph(f"Vous · {ts}", label_style),
                    Paragraph(_md_inline(msg.content), user_bg_style),
                ]
                elements.append(KeepTogether(block))
            else:
                block = [Paragraph(f"LabAssistant · {ts}", label_style)]
                block += _md_to_elements(msg.content, styles)
                elements += block

            elements.append(HRFlowable(
                width='100%', thickness=0.4,
                color=colors.HexColor('#e2e8f0'), spaceAfter=4
            ))

        # ── Footer
        elements += [
            Spacer(1, 0.5*cm),
            Paragraph(
                f"Exporté le {datetime.now().strftime('%d/%m/%Y à %H:%M')} "
                f"— LabAssistant · Poulina Group Holding",
                footer_style
            ),
        ]

        doc.build(elements)
        buffer.seek(0)
        return buffer
