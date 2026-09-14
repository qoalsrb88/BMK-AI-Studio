"""Read-only syntax colouring for prompt editors; the text itself is never modified."""
import re
import weakref
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import QPlainTextEdit
from .appearance import tokens

COMMENT = re.compile(r'^\s*//.*$')
# NovelAI / BMK style weight markers: "1.4::" opens, "::" closes.
NAI_WEIGHT = re.compile(r'(?<![\w.])-?\d+(?:\.\d+)?::|::')
# A1111 style "(tag:1.2)" weights: colour the ":1.2" part.
A1111_WEIGHT = re.compile(r':\s*-?\d+(?:\.\d+)?(?=\s*[)\]])')
EMPHASIS = re.compile(r'[{}\[\]()]')

_instances = weakref.WeakSet()


class PromptHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document); _instances.add(self)

    def highlightBlock(self, text):
        t = tokens()
        if COMMENT.match(text):
            comment = QTextCharFormat(); comment.setForeground(QColor(t['muted'])); comment.setFontItalic(True)
            self.setFormat(0, len(text), comment); return
        weight = QTextCharFormat(); weight.setForeground(QColor(t['accent'])); weight.setFontWeight(QFont.Weight.Bold)
        for match in NAI_WEIGHT.finditer(text): self.setFormat(match.start(), match.end() - match.start(), weight)
        for match in A1111_WEIGHT.finditer(text): self.setFormat(match.start(), match.end() - match.start(), weight)
        marks = QTextCharFormat(); marks.setForeground(QColor(t['muted']))
        for match in EMPHASIS.finditer(text): self.setFormat(match.start(), 1, marks)


def attach(document):
    """One highlighter per document, even when documents are swapped between editors."""
    existing = document.findChild(PromptHighlighter)
    return existing or PromptHighlighter(document)


def refresh_all():
    """Re-run every live highlighter, e.g. after the theme changed."""
    for highlighter in list(_instances): highlighter.rehighlight()


class PromptEdit(QPlainTextEdit):
    """QPlainTextEdit whose current document is always highlighted, including swapped-in documents."""
    def __init__(self, *args):
        super().__init__(*args); attach(self.document())

    def setDocument(self, document):
        super().setDocument(document); attach(document)
