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
    QFrame, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
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
    outer.setSpacing(8)
    outer.setContentsMargins(10, 8, 10, 10)

    # ── Power input row ───────────────────────────────────────────────────────
    power_row = QHBoxLayout()
    power_row.setSpacing(6)
    parent.manual_power_label = QLabel("Power %")
    parent.manual_power_label.setFixedWidth(104)

    parent.manual_percent = QLineEdit()
    parent.manual_percent.setPlaceholderText("0 – 100")
    parent.manual_percent.setFixedHeight(30)
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
    outer.addLayout(power_row)

    parent._manual_param_labels = []
    parent._manual_param_inputs = [parent.manual_percent]
    manual_input_style = parent.manual_percent.styleSheet()

    for label_text, attr in (
        ("Sample rate", "manual_sample_rate"),
        ("Pre laser", "manual_pre_laser"),
        ("Laser duration", "manual_laser_duration"),
        ("After laser", "manual_after_laser"),
    ):
        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel(label_text)
        label.setFixedWidth(104)

        edit = QLineEdit()
        edit.setPlaceholderText("0")
        edit.setFixedHeight(30)
        edit.setStyleSheet(manual_input_style)

        setattr(parent, attr, edit)
        parent._manual_param_labels.append(label)
        parent._manual_param_inputs.append(edit)

        row.addWidget(label)
        row.addWidget(edit)
        outer.addLayout(row)

    # ── Divider ───────────────────────────────────────────────────────────────
    parent.manual_divider = QFrame()
    parent.manual_divider.setVisible(False)

    # ── Grid label ────────────────────────────────────────────────────────────
    parent.manual_grid_label = QLabel("")
    parent.manual_grid_label.setVisible(False)

    # ── 4 × 6 grid  (24 lasers) ───────────────────────────────────────────────
    grid = QGridLayout()
    grid.setSpacing(4)

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
    group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    group.setMinimumHeight(group.sizeHint().height())
    apply_manual_theme(parent)
    return group


# ─── Custom button classes ────────────────────────────────────────────────────

def create_laser_status_box(parent):
    group = QGroupBox("LASER  READBACK")
    lay = QVBoxLayout()
    lay.setContentsMargins(8, 8, 8, 8)
    lay.setSpacing(6)

    table = QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["Laser", "Photo", "Photo current", "Time"])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setFixedHeight(28)
    table.verticalHeader().setDefaultSectionSize(26)

    parent.laser_readback_table = table
    lay.addWidget(table)
    group.setLayout(lay)
    apply_laser_status_theme(parent)
    return group


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
            font-size: 12px;
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
            font-size: 12px;
            font-weight: 800;
        }}
        QPushButton:hover {{
            background-color: {t["laser_active_hover"]};
        }}
    """

    def __init__(self, index: int):
        super().__init__(str(index))
        self._index = index
        self._drive_current = None
        self._photo_current = None
        self.setFixedSize(38, 32)
        self._active = False
        self.setStyleSheet(self._style_idle())

    def set_active(self, active: bool):
        self._active = active
        self.setStyleSheet(self._style_active() if active else self._style_idle())

    def toggle_active(self):
        self.set_active(not self._active)

    def set_drive_current(self, value):
        self._drive_current = value
        self._refresh_text()

    def set_photo_current(self, value):
        self._photo_current = value
        self._refresh_text()

    def _refresh_text(self):
        self.setText(str(self._index))


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
    for label in getattr(parent, "_manual_param_labels", []):
        label.setStyleSheet(label_style)
    parent.manual_grid_label.setStyleSheet(
        f"color: {t['text_secondary']}; font-size: 12px; font-weight: 600;"
    )
    parent.manual_divider.setStyleSheet(
        f"background: {t['border']}; max-height: 1px; border: none;"
    )
    field_style = f"""
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
    """
    for edit in getattr(parent, "_manual_param_inputs", [parent.manual_percent]):
        edit.setStyleSheet(field_style)

    for btn in getattr(parent, "_laser_buttons", {}).values():
        btn.set_active(btn._active)

    parent.manual_all_on_btn.apply_theme()
    parent.manual_all_off_btn.apply_theme()
    apply_laser_status_theme(parent)


def apply_laser_status_theme(parent):
    table = getattr(parent, "laser_readback_table", None)
    if not table:
        return
    t = get_theme()
    table.setStyleSheet(f"""
        QTableWidget {{
            background:{t["bg_card"]};
            border:1.5px solid {t["border"]};
            border-radius:7px;
            color:{t["text_secondary"]};
            gridline-color:{t["border"]};
            font-size:11px;
            font-weight:700;
        }}
        QHeaderView::section {{
            background:{t["bg_surface"]};
            border:none;
            border-right:1px solid {t["border"]};
            border-bottom:1px solid {t["border"]};
            color:{t["accent_cyan"]};
            font-size:11px;
            font-weight:800;
            padding:4px;
        }}
        QTableWidget::item {{
            border:none;
            padding:3px 5px;
        }}
    """)


def _refresh_laser_status(parent, pos=None):
    if pos is not None:
        parent._manual_selected_laser_pos = pos


def append_laser_readback(parent, pos: int, current, started_at: str = None):
    table = getattr(parent, "laser_readback_table", None)
    if table is None:
        return

    row = table.rowCount()
    table.insertRow(row)
    values = [
        f"Laser {pos}",
        f"Photo {pos}",
        _format_current(current),
        started_at or getattr(parent, "_manual_laser_started_at", "--"),
    ]
    for col, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, col, item)
    table.scrollToBottom()


def update_photo_current(parent, pos: int, value):
    """Update PHOTO readback for a laser/photo position."""
    try:
        import global_var
        if not hasattr(global_var, "photo_current"):
            global_var.photo_current = {i: None for i in range(1, 25)}
        global_var.photo_current[pos] = value
    except Exception:
        pass

    btn = getattr(parent, "_laser_buttons", {}).get(pos)
    if btn:
        btn.set_photo_current(value)
    if getattr(parent, "_manual_selected_laser_pos", None) in (None, pos):
        _refresh_laser_status(parent, pos)
    append_laser_readback(
        parent,
        pos,
        value,
        getattr(parent, "_manual_laser_started_at", "--"),
    )


def finish_laser_experiment(parent):
    pos = getattr(parent, "_manual_running_laser_pos", None)
    btn = getattr(parent, "_laser_buttons", {}).get(pos)
    if btn:
        btn.set_active(False)
    parent._manual_running_laser_pos = None


def _set_laser_drive_current(parent, pos: int, value):
    try:
        import global_var
        if not hasattr(global_var, "laser_drive_current"):
            global_var.laser_drive_current = {i: None for i in range(1, 25)}
        global_var.laser_drive_current[pos] = value
    except Exception:
        pass

    btn = getattr(parent, "_laser_buttons", {}).get(pos)
    if btn:
        btn.set_drive_current(value)
    if getattr(parent, "_manual_selected_laser_pos", None) in (None, pos):
        _refresh_laser_status(parent, pos)


def _format_current(value):
    if value is None:
        return "--"
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def laser_click(parent, pos: int):
    """Start one scheduled laser experiment with the exp_start_laser CLI."""
    btn = parent._laser_buttons.get(pos)
    if btn and btn._active:
        _send_uart_command(parent, "exp_end")
        clear_gui_laser_exp_pending(parent)
        btn.set_active(False)
        _set_laser_drive_current(parent, pos, 0)
        parent._manual_running_laser_pos = None
        return

    power_value, sample_rate, pre_laser, laser_duration, after_laser = _manual_exp_params(parent)
    parent._manual_running_laser_pos = pos
    parent._manual_selected_laser_pos = pos
    parent._manual_laser_started_at = _now_text()

    if btn:
        btn.set_active(True)
    _set_laser_drive_current(parent, pos, power_value)
    mark_gui_laser_exp_started(parent)
    _send_uart_command(
        parent,
        f"exp_start_laser {pos} {power_value} {sample_rate} {pre_laser} {laser_duration} {after_laser}",
    )


def fire_all(parent):
    """Start all laser experiments with the selected manual schedule."""
    power_value, sample_rate, pre_laser, laser_duration, after_laser = _manual_exp_params(parent)
    parent._manual_all_drive = power_value
    for pos in range(1, 25):
        btn = parent._laser_buttons.get(pos)
        if btn:
            btn.set_active(True)
        parent._manual_running_laser_pos = pos
        parent._manual_selected_laser_pos = pos
        parent._manual_laser_started_at = _now_text()
        _set_laser_drive_current(parent, pos, power_value)
        mark_gui_laser_exp_started(parent)
        _send_uart_command(
            parent,
            f"exp_start_laser {pos} {power_value} {sample_rate} {pre_laser} {laser_duration} {after_laser}",
        )
    _refresh_laser_status(parent, "ALL")


def off_all(parent):
    """Stop the current experiment and clear active highlights in the GUI."""
    _send_uart_command(parent, "exp_end")
    clear_gui_laser_exp_pending(parent)
    for pos in range(1, 25):
        btn = parent._laser_buttons.get(pos)
        if btn:
            btn.set_active(False)
        _set_laser_drive_current(parent, pos, 0)
    parent._manual_all_drive = 0
    parent._manual_running_laser_pos = None
    _refresh_laser_status(parent, "ALL")


def _manual_power_value(text: str) -> int:
    try:
        percent = float(text.strip() or "0")
    except ValueError:
        percent = 0

    percent = max(0, min(100, percent))
    return round(percent)


def _manual_exp_params(parent):
    return (
        _manual_power_value(parent.manual_percent.text()),
        _manual_nonnegative_int_value(parent.manual_sample_rate.text()),
        _manual_nonnegative_int_value(parent.manual_pre_laser.text()),
        _manual_nonnegative_int_value(parent.manual_laser_duration.text()),
        _manual_nonnegative_int_value(parent.manual_after_laser.text()),
    )


def _manual_nonnegative_int_value(text: str) -> int:
    try:
        value = float(text.strip() or "0")
    except ValueError:
        value = 0

    return max(0, round(value))


def mark_gui_laser_exp_started(parent, count: int = 1):
    pending = getattr(parent, "_manual_gui_laser_exp_pending", 0)
    parent._manual_gui_laser_exp_pending = max(0, pending) + max(0, count)


def consume_gui_laser_exp_pending(parent) -> bool:
    pending = getattr(parent, "_manual_gui_laser_exp_pending", 0)
    if pending <= 0:
        return False

    parent._manual_gui_laser_exp_pending = pending - 1
    return True


def clear_gui_laser_exp_pending(parent):
    parent._manual_gui_laser_exp_pending = 0


def _send_uart_command(parent, cmd: str):
    if hasattr(parent, "uart") and parent.uart:
        parent.uart.send_command(cmd)


def _now_text():
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")
