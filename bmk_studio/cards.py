"""Shared card painting for image grids: rounded hover/selection, two-line captions, badges."""
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QStyle
from .appearance import tokens

TEXT_LINES = 2
PAD = 8


def caption_height(metrics):
    """Vertical space reserved under the thumbnail for the file name."""
    return metrics.lineSpacing() * TEXT_LINES + 12


SEPARATORS = '_-. ·'


def wrap_lines(metrics, text, width):
    """Split `text` into at most two lines for `width`, preferring a break after _ - . or space; the second line is middle-elided."""
    if metrics.horizontalAdvance(text) <= width: return [text]
    cut = len(text)
    while cut > 1 and metrics.horizontalAdvance(text[:cut]) > width: cut = max(1, int(cut * 0.85)) if cut > 8 else cut - 1
    while cut < len(text) and metrics.horizontalAdvance(text[:cut + 1]) <= width: cut += 1
    # Break at the earliest separator in the second half so the two lines stay balanced ("SkinMaskTest_" / "00001_.png").
    for position in range(cut // 2, cut):
        if text[position] in SEPARATORS: cut = position + 1; break
    return [text[:cut], metrics.elidedText(text[cut:], Qt.TextElideMode.ElideMiddle, width)]


def paint_card(painter, option, rect, draw_content, title, badge=None, current=False):
    """Draw one card: `draw_content(painter, content_rect)` paints the thumbnail area; the caption is laid out from the bottom."""
    t = tokens()
    selected = bool(option.state & QStyle.StateFlag.State_Selected); hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
    painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if selected or hover or current:
        path = QPainterPath(); path.addRoundedRect(QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5), 8, 8)
        painter.fillPath(path, QColor(t['selected'] if selected else t['surface2']))
        if selected or current: painter.setPen(QPen(QColor(t['accent']), 2 if selected else 1.2)); painter.drawPath(path)
    metrics = option.fontMetrics; text_height = caption_height(metrics); spacing = metrics.lineSpacing()
    content = rect.adjusted(PAD + 2, PAD, -PAD - 2, -text_height)
    draw_content(painter, content)
    painter.setFont(option.font); painter.setPen(QColor(t['fg']))
    lines = wrap_lines(metrics, title, rect.width() - 2 * PAD)
    y = rect.bottom() - text_height + (text_height - len(lines) * spacing) // 2
    for line in lines:
        painter.drawText(QRect(rect.left() + PAD, y, rect.width() - 2 * PAD, spacing), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, line); y += spacing
    if badge:
        width = metrics.horizontalAdvance(badge) + 12; box = QRectF(content.left(), content.top(), width, 20)
        pill = QPainterPath(); pill.addRoundedRect(box, 10, 10); painter.fillPath(pill, QColor(t['accent']))
        painter.setPen(QColor(t['on_accent'])); painter.drawText(box, Qt.AlignmentFlag.AlignCenter, badge)
    painter.restore()
