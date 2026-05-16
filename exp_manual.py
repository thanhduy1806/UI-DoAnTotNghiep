# from PyQt5.QtWidgets import (
#     QGroupBox, QVBoxLayout,
#     QGridLayout, QPushButton, QLabel, QLineEdit
# )


# def create_manual_group_box(parent):

#     group = QGroupBox("Manual Laser Control")
#     layout = QVBoxLayout()

#     parent.manual_percent = QLineEdit()
#     parent.manual_percent.setPlaceholderText("Laser % (0-100)")

#     layout.addWidget(QLabel("Power"))
#     layout.addWidget(parent.manual_percent)

#     grid = QGridLayout()

#     for i in range(6):
#         for j in range(6):

#             idx = i * 6 + j + 1

#             btn = QPushButton(str(idx))
#             btn.setFixedSize(38, 38)

#             btn.clicked.connect(
#                 lambda _, x=idx: laser_click(parent, x)
#             )

#             grid.addWidget(btn, i, j)

#     layout.addLayout(grid)
#     group.setLayout(layout)

#     return group


# def laser_click(parent, pos):

#     percent = parent.manual_percent.text() or "0"
#     cmd = f"LASER:{pos}:{percent}"

#     if hasattr(parent, "uart"):
#         parent.uart.send_command(cmd)



from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QLineEdit,
    QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from theme import get_theme


# ─── Palette (mirror main_window) ────────────────────────────────────────────
BG_SURFACE  = "#131B2A"
BORDER      = "#2B3B5E"
ACCENT_CYAN = "#00C8E8"
ACCENT_TEAL = "#00E5B0"
ACCENT_WARN = "#F59E0B"
ACCENT_ERR  = "#FF5C5C"
TEXT_PRIM   = "#F4F8FF"
TEXT_SEC    = "#B9C7DD"


def create_manual_group_box(parent):
    group = QGroupBox("LASER CONTROL  —  MANUAL")
    outer = QVBoxLayout()
    outer.setSpacing(10)
    outer.setContentsMargins(10, 10, 10, 10)

    # ── Power input row ───────────────────────────────────────────────────────
    power_row = QHBoxLayout()
    parent.manual_power_label = QLabel("Power %")
    parent.manual_power_label.setFixedWidth(72)

    parent.manual_percent = QLineEdit()
    parent.manual_percent.setPlaceholderText("0 – 100")
    parent.manual_percent.setFixedHeight(34)
    parent.manual_percent.setStyleSheet(f"""
        QLineEdit {{
            background: {BG_SURFACE};
            border: 1.5px solid {BORDER};
            border-radius: 6px;
            color: {ACCENT_CYAN};
            font-size: 14px;
            font-weight: 700;
            padding: 3px 10px;
        }}
        QLineEdit:focus {{ border-color: {ACCENT_CYAN}; }}
    """)

    parent.manual_pct_unit = QLabel("%")

    power_row.addWidget(parent.manual_power_label)
    power_row.addWidget(parent.manual_percent)
    power_row.addWidget(parent.manual_pct_unit)
    outer.addLayout(power_row)

    # ── Divider ───────────────────────────────────────────────────────────────
    parent.manual_divider = QFrame()
    parent.manual_divider.setFrameShape(QFrame.HLine)
    outer.addWidget(parent.manual_divider)

    # ── Grid label ────────────────────────────────────────────────────────────
    parent.manual_grid_label = QLabel("Select laser position  (1 – 24)")
    outer.addWidget(parent.manual_grid_label)

    # ── 4 × 6 grid  (24 lasers) ───────────────────────────────────────────────
    grid = QGridLayout()
    grid.setSpacing(5)

    parent._laser_buttons = {}

    for pos in range(1, 25):          # 1 … 24
        row = (pos - 1) // 6
        col = (pos - 1) % 6

        btn = _LaserButton(pos)
        btn.clicked.connect(lambda _, x=pos: laser_click(parent, x))

        grid.addWidget(btn, row, col)
        parent._laser_buttons[pos] = btn

    outer.addLayout(grid)

    # ── Quick-fire row ────────────────────────────────────────────────────────
    qf_row = QHBoxLayout()
    qf_row.setSpacing(6)

    parent.manual_all_on_btn = _ActionButton("ALL ON", "on")
    parent.manual_all_on_btn.clicked.connect(lambda: fire_all(parent))

    parent.manual_all_off_btn = _ActionButton("ALL OFF", "off")
    parent.manual_all_off_btn.clicked.connect(lambda: off_all(parent))

    qf_row.addWidget(parent.manual_all_on_btn)
    qf_row.addWidget(parent.manual_all_off_btn)
    outer.addLayout(qf_row)

    group.setLayout(outer)
    apply_manual_theme(parent)
    return group


# ─── Custom button classes ────────────────────────────────────────────────────

class _LaserButton(QPushButton):
    """Compact numbered laser button with active / inactive states."""

    @staticmethod
    def _style_idle():
        t = get_theme()
        return f"""
        QPushButton {{
            background-color: {t["bg_surface"]};
            border: 1.5px solid {t["border"]};
            border-radius: 6px;
            color: {t["laser_idle_text"]};
            font-size: 13px;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background-color: {t["hover_surface"]};
            border-color: {t["accent_cyan"]};
            color: {t["laser_hover_text"]};
        }}
        QPushButton:pressed {{
            background-color: {t["laser_pressed"]};
        }}
    """

    @staticmethod
    def _style_active():
        t = get_theme()
        return f"""
        QPushButton {{
            background-color: {t["laser_active_bg"]};
            border: 1.5px solid {t["accent_teal"]};
            border-radius: 6px;
            color: {t["accent_teal"]};
            font-size: 13px;
            font-weight: 800;
        }}
        QPushButton:hover {{
            background-color: {t["laser_active_hover"]};
        }}
    """

    def __init__(self, index: int):
        super().__init__(str(index))
        self.setFixedSize(44, 42)
        self._active = False
        self.setStyleSheet(self._style_idle())

    def set_active(self, active: bool):
        self._active = active
        self.setStyleSheet(self._style_active() if active else self._style_idle())

    def toggle_active(self):
        self.set_active(not self._active)


class _ActionButton(QPushButton):
    """Wider action button (All On / All Off) with accent colour."""

    def __init__(self, label: str, role: str):
        super().__init__(label)
        self._role = role
        self.setFixedHeight(36)
        self.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.apply_theme()

    def apply_theme(self):
        t = get_theme()
        if self._role == "on":
            accent = t["accent_cyan"]
            bg = t["all_on_bg"]
            hover_bg = t["all_on_hover"]
            pressed_bg = t["all_on_pressed"]
        else:
            accent = t["accent_warn"]
            bg = t["all_off_bg"]
            hover_bg = t["all_off_hover"]
            pressed_bg = t["all_off_pressed"]

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: 1.5px solid {accent};
                border-radius: 6px;
                color: {t["text_primary"]};
                font-size: 13px;
                font-weight: 800;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border-color: {accent};
            }}
            QPushButton:pressed {{
                background-color: {pressed_bg};
            }}
        """)


# ─── Handlers ────────────────────────────────────────────────────────────────

def apply_manual_theme(parent):
    if not hasattr(parent, "manual_percent"):
        return

    t = get_theme()
    label_style = f"color: {t['text_secondary']}; font-size: 13px; font-weight: 600;"
    parent.manual_power_label.setStyleSheet(label_style)
    parent.manual_pct_unit.setStyleSheet(label_style)
    parent.manual_grid_label.setStyleSheet(
        f"color: {t['text_secondary']}; font-size: 12px; font-weight: 600;"
    )
    parent.manual_divider.setStyleSheet(
        f"background: {t['border']}; max-height: 1px; border: none;"
    )
    parent.manual_percent.setStyleSheet(f"""
        QLineEdit {{
            background: {t["bg_surface"]};
            border: 1.5px solid {t["border"]};
            border-radius: 6px;
            color: {t["accent_cyan"]};
            font-size: 14px;
            font-weight: 700;
            padding: 3px 10px;
        }}
        QLineEdit:focus {{ border-color: {t["accent_cyan"]}; }}
    """)

    for btn in getattr(parent, "_laser_buttons", {}).values():
        btn.set_active(btn._active)

    parent.manual_all_on_btn.apply_theme()
    parent.manual_all_off_btn.apply_theme()


def laser_click(parent, pos: int):
    """Toggle a single laser and send the CLI command over UART."""
    btn = parent._laser_buttons.get(pos)
    if btn:
        btn.toggle_active()

    is_on   = btn._active if btn else True

    if is_on:
        _send_laser_dac(parent)
        _send_uart_command(parent, f"laser_int_sw_on {pos}")
    else:
        _send_uart_command(parent, f"laser_int_sw_off {pos}")


def fire_all(parent):
    """Turn all 24 lasers ON."""
    for pos in range(1, 25):
        btn = parent._laser_buttons.get(pos)
        if btn:
            btn.set_active(True)
    _send_laser_dac(parent)
    for pos in range(1, 25):
        _send_uart_command(parent, f"laser_int_sw_on {pos}")


def off_all(parent):
    """Turn all 24 lasers OFF."""
    for pos in range(1, 25):
        btn = parent._laser_buttons.get(pos)
        if btn:
            btn.set_active(False)
    for pos in range(1, 25):
        _send_uart_command(parent, f"laser_int_sw_off {pos}")


def _send_laser_dac(parent):
    power_value = _manual_power_value(parent.manual_percent.text())
    _send_uart_command(parent, f"laser_int_set_dac {power_value}")


def _manual_power_value(text: str) -> int:
    try:
        percent = float(text.strip() or "0")
    except ValueError:
        percent = 0

    percent = max(0, min(100, percent))
    return round(percent)


def _send_uart_command(parent, cmd: str):
    if hasattr(parent, "uart") and parent.uart:
        parent.uart.send_command(cmd)
