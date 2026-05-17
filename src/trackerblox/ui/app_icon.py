from __future__ import annotations

from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap


def build_app_icon(size: int = 64) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor("#18212B"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QColor("#243445"))
    painter.setBrush(QColor("#243445"))
    painter.drawRoundedRect(6, 6, 52, 52, 14, 14)
    painter.fillRect(18, 16, 6, 32, QColor("#57D19A"))
    painter.fillRect(30, 24, 6, 24, QColor("#F2C14E"))
    painter.fillRect(42, 12, 6, 36, QColor("#F78154"))
    painter.end()
    return QIcon(pixmap)