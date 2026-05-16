# from PyQt5.QtWidgets import (
#     QGroupBox, QVBoxLayout, QHBoxLayout,
#     QPushButton, QLabel, QLineEdit,
#     QFrame, QSizePolicy
# )
# from PyQt5.QtCore import Qt


# # ─── Palette ──────────────────────────────────────────────────────────────────
# BG_SURFACE  = "#111520"
# BORDER      = "#1E2840"
# ACCENT_CYAN = "#00C8E8"
# ACCENT_TEAL = "#00E5B0"
# ACCENT_ERR  = "#FF5C5C"
# TEXT_PRIM   = "#E8ECF4"
# TEXT_SEC    = "#7A8BA8"


# def _field_row(label_text: str, widget) -> QHBoxLayout:
#     """Utility: return a label + widget row."""
#     row = QHBoxLayout()
#     lbl = QLabel(label_text)
#     lbl.setFixedWidth(55)
#     lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px;")
#     row.addWidget(lbl)
#     row.addWidget(widget)
#     return row


# def _input(placeholder: str, default: str = "") -> QLineEdit:
#     e = QLineEdit(default)
#     e.setPlaceholderText(placeholder)
#     e.setFixedHeight(28)
#     e.setStyleSheet(f"""
#         QLineEdit {{
#             background: {BG_SURFACE};
#             border: 1px solid {BORDER};
#             border-radius: 6px;
#             color: {ACCENT_CYAN};
#             font-size: 12px;
#             font-weight: 600;
#             padding: 2px 8px;
#         }}
#         QLineEdit:focus {{ border-color: {ACCENT_CYAN}; }}
#     """)
#     return e


# def create_auto_group_box(parent):
#     group = QGroupBox("LASER CONTROL  —  AUTO")
#     outer = QVBoxLayout()
#     outer.setSpacing(10)
#     outer.setContentsMargins(10, 10, 10, 10)

#     # ── Fields ────────────────────────────────────────────────────────────────
#     parent.exp_start   = _input("Start position", "1")
#     parent.exp_end     = _input("End position",   "24")
#     parent.exp_percent = _input("Power %",        "50")

#     outer.addLayout(_field_row("Start",  parent.exp_start))
#     outer.addLayout(_field_row("End",    parent.exp_end))
#     outer.addLayout(_field_row("Power",  parent.exp_percent))

#     # ── Divider ───────────────────────────────────────────────────────────────
#     div = QFrame()
#     div.setFrameShape(QFrame.HLine)
#     div.setStyleSheet(f"background: {BORDER}; max-height: 1px; border: none;")
#     outer.addWidget(div)

#     # ── Status hint ───────────────────────────────────────────────────────────
#     parent.auto_status = QLabel("Ready")
#     parent.auto_status.setAlignment(Qt.AlignCenter)
#     parent.auto_status.setStyleSheet(f"""
#         color: {TEXT_SEC};
#         font-size: 10px;
#         font-style: italic;
#     """)
#     outer.addWidget(parent.auto_status)

#     # ── Start / Stop buttons ──────────────────────────────────────────────────
#     btn_row = QHBoxLayout()
#     btn_row.setSpacing(6)

#     start_btn = QPushButton("▶  START")
#     start_btn.setFixedHeight(34)
#     start_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#     start_btn.setStyleSheet(f"""
#         QPushButton {{
#             background-color: {ACCENT_TEAL}18;
#             border: 1px solid {ACCENT_TEAL}60;
#             border-radius: 7px;
#             color: {ACCENT_TEAL};
#             font-size: 12px;
#             font-weight: 700;
#             letter-spacing: 1px;
#         }}
#         QPushButton:hover {{
#             background-color: {ACCENT_TEAL}30;
#             border-color: {ACCENT_TEAL};
#         }}
#         QPushButton:pressed {{
#             background-color: {ACCENT_TEAL}12;
#         }}
#     """)
#     start_btn.clicked.connect(lambda: start_experiment(parent))

#     stop_btn = QPushButton("■  STOP")
#     stop_btn.setFixedHeight(34)
#     stop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
#     stop_btn.setStyleSheet(f"""
#         QPushButton {{
#             background-color: {ACCENT_ERR}18;
#             border: 1px solid {ACCENT_ERR}60;
#             border-radius: 7px;
#             color: {ACCENT_ERR};
#             font-size: 12px;
#             font-weight: 700;
#             letter-spacing: 1px;
#         }}
#         QPushButton:hover {{
#             background-color: {ACCENT_ERR}30;
#             border-color: {ACCENT_ERR};
#         }}
#         QPushButton:pressed {{
#             background-color: {ACCENT_ERR}12;
#         }}
#     """)
#     stop_btn.clicked.connect(lambda: stop_experiment(parent))

#     btn_row.addWidget(start_btn)
#     btn_row.addWidget(stop_btn)
#     outer.addLayout(btn_row)

#     group.setLayout(outer)
#     return group


# # ─── Handlers ────────────────────────────────────────────────────────────────

# def start_experiment(parent):
#     s = parent.exp_start.text().strip()   or "1"
#     e = parent.exp_end.text().strip()     or "24"
#     p = parent.exp_percent.text().strip() or "50"

#     cmd = f"AUTO:{s}:{e}:{p}"

#     if hasattr(parent, "auto_status"):
#         parent.auto_status.setText(f"Running  {s} → {e}  @ {p}%")
#         parent.auto_status.setStyleSheet(
#             f"color: #00E5B0; font-size: 10px; font-style: italic;"
#         )

#     if hasattr(parent, "uart"):
#         parent.uart.send_command(cmd)


# def stop_experiment(parent):
#     if hasattr(parent, "auto_status"):
#         parent.auto_status.setText("Stopped")
#         parent.auto_status.setStyleSheet(
#             f"color: #FF5C5C; font-size: 10px; font-style: italic;"
#         )
#     if hasattr(parent, "uart"):
#         parent.uart.send_command("AUTO:STOP")


from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit,
    QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt


# ─── Palette ──────────────────────────────────────────────────────────────────
BG_SURFACE  = "#131B2A"
BORDER      = "#2B3B5E"
ACCENT_CYAN = "#00C8E8"
ACCENT_TEAL = "#00E5B0"
ACCENT_ERR  = "#FF5C5C"
TEXT_PRIM   = "#F4F8FF"
TEXT_SEC    = "#B9C7DD"


def _field_row(label_text: str, widget) -> QHBoxLayout:
    """Utility: return a label + widget row."""
    row = QHBoxLayout()
    lbl = QLabel(label_text)
    lbl.setFixedWidth(70)
    lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 13px; font-weight: 600;")
    row.addWidget(lbl)
    row.addWidget(widget)
    return row


def _input(placeholder: str, default: str = "") -> QLineEdit:
    e = QLineEdit(default)
    e.setPlaceholderText(placeholder)
    e.setFixedHeight(34)
    e.setStyleSheet(f"""
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
    return e


def create_auto_group_box(parent):
    group = QGroupBox("LASER CONTROL  —  AUTO")
    outer = QVBoxLayout()
    outer.setSpacing(10)
    outer.setContentsMargins(10, 10, 10, 10)

    # ── Fields ────────────────────────────────────────────────────────────────
    parent.exp_start   = _input("Start position", "1")
    parent.exp_end     = _input("End position",   "24")
    parent.exp_percent = _input("Power %",        "50")

    outer.addLayout(_field_row("Start",  parent.exp_start))
    outer.addLayout(_field_row("End",    parent.exp_end))
    outer.addLayout(_field_row("Power",  parent.exp_percent))

    # ── Divider ───────────────────────────────────────────────────────────────
    div = QFrame()
    div.setFrameShape(QFrame.HLine)
    div.setStyleSheet(f"background: {BORDER}; max-height: 1px; border: none;")
    outer.addWidget(div)

    # ── Status hint ───────────────────────────────────────────────────────────
    parent.auto_status = QLabel("Ready")
    parent.auto_status.setAlignment(Qt.AlignCenter)
    parent.auto_status.setStyleSheet(f"""
        color: {TEXT_SEC};
        font-size: 13px;
        font-weight: 600;
        font-style: italic;
    """)
    outer.addWidget(parent.auto_status)

    # ── Start / Stop buttons ──────────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_row.setSpacing(6)

    start_btn = QPushButton("START")
    start_btn.setFixedHeight(38)
    start_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    start_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {ACCENT_TEAL}34;
            border: 1.5px solid {ACCENT_TEAL}90;
            border-radius: 7px;
            color: #F4F8FF;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.4px;
        }}
        QPushButton:hover {{
            background-color: {ACCENT_TEAL}48;
            border-color: {ACCENT_TEAL};
        }}
        QPushButton:pressed {{
            background-color: {ACCENT_TEAL}12;
        }}
    """)
    start_btn.clicked.connect(lambda: start_experiment(parent))

    stop_btn = QPushButton("STOP")
    stop_btn.setFixedHeight(38)
    stop_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    stop_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {ACCENT_ERR}34;
            border: 1.5px solid {ACCENT_ERR}90;
            border-radius: 7px;
            color: #F4F8FF;
            font-size: 13px;
            font-weight: 800;
            letter-spacing: 0.4px;
        }}
        QPushButton:hover {{
            background-color: {ACCENT_ERR}48;
            border-color: {ACCENT_ERR};
        }}
        QPushButton:pressed {{
            background-color: {ACCENT_ERR}12;
        }}
    """)
    stop_btn.clicked.connect(lambda: stop_experiment(parent))

    btn_row.addWidget(start_btn)
    btn_row.addWidget(stop_btn)
    outer.addLayout(btn_row)

    group.setLayout(outer)
    return group


# ─── Handlers ────────────────────────────────────────────────────────────────

def start_experiment(parent):
    s = parent.exp_start.text().strip()   or "1"
    e = parent.exp_end.text().strip()     or "24"
    p = parent.exp_percent.text().strip() or "50"

    cmd = f"AUTO:{s}:{e}:{p}"

    if hasattr(parent, "auto_status"):
        parent.auto_status.setText(f"Running  {s} → {e}  @ {p}%")
        parent.auto_status.setStyleSheet(
            f"color: #00E5B0; font-size: 13px; font-weight: 600; font-style: italic;"
        )

    if hasattr(parent, "uart"):
        parent.uart.send_command(cmd)


def stop_experiment(parent):
    if hasattr(parent, "auto_status"):
        parent.auto_status.setText("Stopped")
        parent.auto_status.setStyleSheet(
            f"color: #FF5C5C; font-size: 13px; font-weight: 600; font-style: italic;"
        )
    if hasattr(parent, "uart"):
        parent.uart.send_command("AUTO:STOP")
