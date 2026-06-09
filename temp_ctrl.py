# temp_ctrl_ui.py  —  v5
# - Theme sáng hơn, chữ to dễ đọc
# - Target line vẽ đúng shape từng step
# - Mode tự động (firmware quyết định), GUI không cần chọn
# - Wizard state machine: chờ prompt firmware → mới gửi

from PyQt5.QtWidgets import (
    QWidget, QGroupBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QSpinBox, QDoubleSpinBox,
    QTextEdit, QSizePolicy, QScrollArea, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal
import pyqtgraph as pg
import numpy as np
import time
import re
from theme import get_theme

# ─── Palette (sáng hơn, dễ đọc) ──────────────────────────────────────────────
# BG_SURFACE  = "#141C2E"
# BG_CARD     = "#1A2340"
# BORDER      = "#2E4070"
# ACCENT_CYAN = "#18E4FF"
# ACCENT_TEAL = "#00FFB2"
# ACCENT_WARN = "#FFBE4A"
# ACCENT_ERR  = "#FF6B6B"
# ACCENT_PRP  = "#A78BFF"
# TEXT_PRIM   = "#FFFFFF"
# TEXT_SEC    = "#C8D8F0"
# TEXT_DIM    = "#7090B8"

# BG_SURFACE  = "#F8FAFC"
# BG_CARD     = "#FFFFFF"
# BORDER      = "#CBD5E1"
# ACCENT_CYAN = "#0284C8"
# ACCENT_TEAL = "#0F766E"
# ACCENT_WARN = "#D97706"
# ACCENT_ERR  = "#DC2626"
# ACCENT_PRP  = "#7C3AED"
# TEXT_PRIM   = "#0F172A"
# TEXT_SEC    = "#334155"
# TEXT_DIM    = "#64748B"

BG_SURFACE  = "#131B2A"
BG_CARD     = "#1B2740"
BORDER      = "#385077"
ACCENT_CYAN = "#00C8E8"
ACCENT_TEAL = "#00E5B0"
ACCENT_WARN = "#F59E0B"
ACCENT_ERR  = "#FF5555"
ACCENT_PRP  = "#BD93F9"
TEXT_PRIM   = "#F4F8FF"
TEXT_SEC    = "#DCE7F7"
TEXT_DIM    = "#AFC0D8"

# BG_SURFACE  = "#1A0F2E"
# BG_CARD     = "#2A1B4A"
# BORDER      = "#5B3FA8"
# ACCENT_CYAN = "#00F5FF"
# ACCENT_TEAL = "#00FFAA"
# ACCENT_WARN = "#FFDD33"
# ACCENT_ERR  = "#FF3366"
# ACCENT_PRP  = "#BB77FF"
# TEXT_PRIM   = "#FFFFFF"
# TEXT_SEC    = "#E0CCFF"
# TEXT_DIM    = "#A388E0"
# ─── Font Size Global ─────────────────────────────────────
FONT_BASE = 14      # ← CHỈNH SỐ NÀY (mặc định 13)

STEP_COLORS = {
    "NONE": ("#1E2840", "#90A8C8"),
    "HEAT": ("#3A1800", "#FFBE4A"),
    "COOL": ("#00223A", "#18E4FF"),
    "SOAK": ("#003020", "#00FFB2"),
}

MAX_STEPS        = 8
WIZARD_TIMEOUT_MS = 10000   # 10s timeout mỗi bước
PID_TIME_WINDOW_SECONDS = 300
PROFILE_CURVE_COLORS = [
    "#00E5B0", "#00C8E8", "#F59E0B", "#BD93F9",
    "#FF5C5C", "#60A5FA", "#A3E635", "#F472B6",
]
PID_WHEEL_ZOOM_IN_FACTOR = 0.88
PID_MIN_TIME_WINDOW_SECONDS = 1.0
PID_MIN_TEMP_WINDOW = 0.05


class _PidGraphViewBox(pg.ViewBox):
    def __init__(self, ui_parent, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pid_ui_parent = ui_parent

    def wheelEvent(self, ev, axis=None):
        _wheel_zoom_pid_plot(self._pid_ui_parent, self, ev, zoom_x=True, zoom_y=True)

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._is_pid_plot_area_pos(ev.pos()):
            _move_pid_measure_cursor(self._pid_ui_parent, self, ev.pos(), advance=True)
            ev.accept()
            return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev, axis=None):
        if axis is None and ev.button() == Qt.LeftButton and self._is_pid_plot_area_pos(ev.pos()):
            advance = hasattr(ev, "isStart") and ev.isStart()
            _move_pid_measure_cursor(self._pid_ui_parent, self, ev.pos(), advance=advance)
            ev.accept()
            return
        super().mouseDragEvent(ev, axis=axis)

    def _is_pid_plot_area_pos(self, pos):
        return self.boundingRect().contains(pos)


class _PidGraphAxis(pg.AxisItem):
    def __init__(self, orientation, ui_parent, *args, **kwargs):
        super().__init__(orientation, *args, **kwargs)
        self._pid_ui_parent = ui_parent

    def wheelEvent(self, ev):
        vb = self.linkedView()
        if vb is None:
            ev.ignore()
            return
        if self.orientation in ("bottom", "top"):
            _wheel_zoom_pid_plot(self._pid_ui_parent, vb, ev, zoom_x=True, zoom_y=False)
        elif self.orientation in ("left", "right"):
            _wheel_zoom_pid_plot(self._pid_ui_parent, vb, ev, zoom_x=False, zoom_y=True)
        else:
            ev.ignore()


class _PidMeasureLabel(pg.TextItem):
    def __init__(self, ui_parent, measure_index, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pid_ui_parent = ui_parent
        self._pid_measure_index = measure_index

    def mouseClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            _hide_pid_measure_cursor(self._pid_ui_parent, self._pid_measure_index)
            ev.accept()
            return
        ev.ignore()


# ═══════════════════════════════════════════════════════════════════════════════
# WIZARD STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════════════

def apply_temp_ctrl_theme():
    global BG_SURFACE, BG_CARD, BORDER
    global ACCENT_CYAN, ACCENT_TEAL, ACCENT_WARN, ACCENT_ERR, ACCENT_PRP
    global TEXT_PRIM, TEXT_SEC, TEXT_DIM, STEP_COLORS

    t = get_theme()
    BG_SURFACE = t["bg_panel"]
    BG_CARD = t["bg_card"]
    BORDER = t["border"]
    ACCENT_CYAN = t["accent_cyan"]
    ACCENT_TEAL = t["accent_teal"]
    ACCENT_WARN = t["accent_warn"]
    ACCENT_ERR = t["accent_err"]
    ACCENT_PRP = t["accent_prp"]
    TEXT_PRIM = t["text_primary"]
    TEXT_SEC = t["text_secondary"]
    TEXT_DIM = t["text_secondary"]

    if t["bg_deep"] == "#EEF4F8":
        STEP_COLORS = {
            "NONE": ("#E8F2F7", "#4F6378"),
            "HEAT": ("#F6E6C9", ACCENT_WARN),
            "COOL": ("#D9F1F7", ACCENT_CYAN),
            "SOAK": ("#D7F4EE", ACCENT_TEAL),
        }
    else:
        STEP_COLORS = {
            "NONE": ("#1E2840", "#90A8C8"),
            "HEAT": ("#3A1800", "#FFBE4A"),
            "COOL": ("#00223A", "#18E4FF"),
            "SOAK": ("#003020", "#00FFB2"),
        }


class WizardStateMachine(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, parent, start_cmd: str, seq: list):
        super().__init__()
        self._parent = parent
        self._start_cmd = start_cmd
        self._seq    = seq
        self._idx    = 0
        self._active = False
        self._seen_saved = False

        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

    def start(self):
        self._active = True
        self._idx    = 0
        self._seen_saved = False
        _send(self._parent, self._start_cmd)
        _log_resp(self._parent, f"[WIZ] Started — Waiting for first prompt...")
        self._reset_timeout()

    def feed_line(self, line: str):
        if not self._active:
            return

        line_l = line.lower()
        if "saved" in line_l:
            self._seen_saved = True

        # Nếu đã gửi hết kịch bản chính, kiểm tra tín hiệu kết thúc
        if self._idx >= len(self._seq):
            if self._seen_saved and "debug@mcu" in line_l:
                self._finish(True, "Profile saved ✓")
            return

        # Chiến lược "Trigger Search": Duyệt từ bước hiện tại để tìm trigger khớp
        # Điều này giúp xử lý vấn đề SSH lag/jitter khi prompts bị gộp hoặc đến chậm
        for i in range(self._idx, len(self._seq)):
            trigger, resp = self._seq[i]
            if trigger.lower() in line_l:
                # Cập nhật index và gửi phản hồi tương ứng
                self._idx = i + 1
                _log_resp(self._parent, f"[WIZ {self._idx}/{len(self._seq)}] Match: '{trigger}' → Sending: '{resp}'")
                _send(self._parent, resp)
                self._reset_timeout()
                return  # Đã phản hồi xong cho dòng này

        for i in range(0, self._idx):
            trigger, resp = self._seq[i]
            if not trigger.lower().startswith("step["):
                continue
            if trigger.lower() not in line_l:
                continue
            _log_resp(self._parent, f"[WIZ {self._idx}/{len(self._seq)}] Retry: '{trigger}' â†’ Sending: '{resp}'")
            _send(self._parent, resp)
            self._reset_timeout()
            return

    def cancel(self):
        self._active = False
        self._timeout.stop()

    def is_active(self):
        return self._active

    def _reset_timeout(self):
        self._timeout.stop()
        self._timeout.start(WIZARD_TIMEOUT_MS)

    def _on_timeout(self):
        self._finish(False,
                     f"Timeout at step {self._idx}/{len(self._seq)} — "
                     "firmware did not respond")

    def _finish(self, ok, msg):
        self._active = False
        self._timeout.stop()
        self.finished.emit(ok, msg)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC BUILDER
# ═══════════════════════════════════════════════════════════════════════════════

def create_temp_ctrl_tab(parent) -> QWidget:
    apply_temp_ctrl_theme()
    parent._wizard_sm = None
    # Khởi tạo global_var an toàn
    import global_var
    for var in ['pid_pv_history', 'pid_time_history', 'pid_target_history',
                'pid_target_history_time', 'pid_target_profile']:
        if not hasattr(global_var, var):
            setattr(global_var, var, [])
    for var in ['pid_profile_time_history', 'pid_profile_pv_history',
                'pid_profile_sp_history', 'pid_profile_err_history',
                'pid_profile_out_history']:
        if not hasattr(global_var, var):
            setattr(global_var, var, {i: [] for i in range(8)})
    if not hasattr(global_var, 'pid_profile_latest'):
        global_var.pid_profile_latest = {
            i: {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0}
            for i in range(8)
        }
    if not hasattr(global_var, 'pid_start_time'):
        global_var.pid_start_time = None
    if not hasattr(global_var, 'pid_graph_session_active'):
        global_var.pid_graph_session_active = False

    root = QScrollArea()
    root.setWidgetResizable(True)
    root.setStyleSheet("QScrollArea{border:none;background:transparent;}")

    inner = QWidget()
    lay   = QVBoxLayout(inner)
    lay.setSpacing(10)
    lay.setContentsMargins(6, 6, 6, 6)

    # Disabled per user request:
    # lay.addWidget(_build_pid_monitor(parent))
    lay.addWidget(_build_profile_overview_table(parent))
    lay.addWidget(_build_pid_graph(parent))
    lay.addWidget(_build_profile_wizard(parent))
    lay.addWidget(_build_run_section(parent))
    # Disabled per user request:
    # lay.addWidget(_build_response_box(parent), stretch=1)

    root.setWidget(inner)
    return root


# ═══════════════════════════════════════════════════════════════════════════════
# A.  PID MONITOR
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pid_monitor(parent) -> QGroupBox:
    grp = _grp("PID  MONITOR  —  REALTIME")
    lay = QVBoxLayout()
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(10)

    parent.pid_step_badge = _StepBadge()
    lay.addWidget(parent.pid_step_badge)

    row = QHBoxLayout()
    row.setSpacing(8)
    parent.pid_card_sp  = _MetricCard("SET POINT", "°C", ACCENT_CYAN)
    parent.pid_card_pv  = _MetricCard("MEASURED",  "°C", ACCENT_TEAL)
    parent.pid_card_err = _MetricCard("ERROR",     "°C", ACCENT_WARN)
    parent.pid_card_out = _MetricCard("OUTPUT",    "%",  ACCENT_PRP)
    for c in (parent.pid_card_sp, parent.pid_card_pv,
              parent.pid_card_err, parent.pid_card_out):
        row.addWidget(c)
    lay.addLayout(row)
    grp.setLayout(lay)
    return grp


# ═══════════════════════════════════════════════════════════════════════════════
def _build_profile_overview_table(parent) -> QGroupBox:
    grp = _grp("PROFILES  OVERVIEW")
    lay = QVBoxLayout()
    lay.setContentsMargins(8, 8, 8, 8)

    table = QTableWidget(8, 6)
    table.setHorizontalHeaderLabels([
        "Profile", "Step", "Set Point °C",
        "Measured °C", "Error °C", "Output %"
    ])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    table.setFixedHeight(270)
    table.setStyleSheet(_pid_table_style())
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setFixedHeight(30)
    table.verticalHeader().setDefaultSectionSize(28)

    parent.pid_profile_table = table
    parent.pid_profile_table_items = {}
    for row in range(8):
        for col in range(6):
            item = QTableWidgetItem()
            item.setTextAlignment(Qt.AlignCenter)
            table.setItem(row, col, item)
        table.item(row, 0).setText(f"P{row}")
        parent.pid_profile_table_items[row] = {
            "step": table.item(row, 1),
            "sp": table.item(row, 2),
            "pv": table.item(row, 3),
            "err": table.item(row, 4),
            "out": table.item(row, 5),
        }

    _refresh_pid_profile_table(parent)
    lay.addWidget(table)
    grp.setLayout(lay)
    return grp


# B.  PID GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pid_graph(parent) -> QGroupBox:
    grp = _grp("TEMPERATURE  GRAPH")
    lay = QVBoxLayout()
    lay.setContentsMargins(8, 8, 8, 8)

    pg.setConfigOptions(antialias=True)
    pw = pg.PlotWidget(
        viewBox=_PidGraphViewBox(parent),
        axisItems={
            "left": _PidGraphAxis("left", parent),
            "bottom": _PidGraphAxis("bottom", parent),
        },
    )
    pw.setBackground(BG_CARD)
    pw.setFixedHeight(430)
    pw.showGrid(x=True, y=True, alpha=0.18)
    pw.setLabel("left",   "°C",     color=TEXT_SEC, size="11pt")
    pw.setLabel("bottom", "Time (s)", color=TEXT_SEC, size="11pt")
    pw.getViewBox().setMouseEnabled(x=True, y=True)

    for name in ("left", "bottom"):
        ax = pw.getAxis(name)
        ax.setPen(pg.mkPen(color=BORDER, width=1))
        ax.setTextPen(pg.mkPen(color=TEXT_SEC))
        ax.setStyle(tickFont=pg.QtGui.QFont("Segoe UI", 10))

    pw.addLegend(
        offset=(10, 10),
        labelTextColor=TEXT_SEC,
        pen=pg.mkPen(color=BORDER),
        brush=pg.mkBrush(BG_SURFACE + "DD"),
    )

    empty = np.array([], dtype=float)

    # PV — đường đo thực tế, nét liền xanh lá
    parent.pid_profile_curves = {}
    for profile_id, color in enumerate(PROFILE_CURVE_COLORS):
        key = f"p{profile_id}"
        curve = pw.plot(
            empty,
            empty,
            pen=pg.mkPen(color=color, width=2.2),
            name=f"P{profile_id}",
        )
        parent.pid_profile_curves[profile_id] = curve
        setattr(parent, f"pid_curve_{key}", curve)

    parent._pid_measure_cursors = []
    parent._pid_measure_active_index = None
    for measure_index, (name, color) in enumerate((("A", ACCENT_CYAN), ("B", ACCENT_WARN))):
        measure_pen = pg.mkPen(color=color, width=1, style=Qt.DashLine)
        x_line = pg.InfiniteLine(angle=90, movable=False, pen=measure_pen)
        y_line = pg.InfiniteLine(angle=0, movable=False, pen=measure_pen)
        label = _PidMeasureLabel(
            parent,
            measure_index,
            color=TEXT_PRIM,
            fill=pg.mkBrush(BG_SURFACE + "E8"),
            border=pg.mkPen(color=color),
            anchor=(0, 1),
        )
        cursor = {
            "name": name,
            "x_line": x_line,
            "y_line": y_line,
            "label": label,
            "point": None,
        }
        parent._pid_measure_cursors.append(cursor)
        for item in (x_line, y_line, label):
            item.setZValue(20 + measure_index)
            item.hide()
            pw.addItem(item, ignoreBounds=True)

    parent._pid_measure_x_line = parent._pid_measure_cursors[0]["x_line"]
    parent._pid_measure_y_line = parent._pid_measure_cursors[0]["y_line"]
    parent._pid_measure_label = parent._pid_measure_cursors[0]["label"]

    parent._pid_plot_widget = pw
    parent._pid_follow_latest = True
    parent._pid_time_window_seconds = PID_TIME_WINDOW_SECONDS
    lay.addWidget(pw)

    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    ar = _text_btn("Auto range", TEXT_SEC, hover=ACCENT_CYAN)
    ar.clicked.connect(lambda: _auto_range_pid_plot(parent))
    all_btn = _curve_toggle_btn("ALL OFF", ACCENT_CYAN, checked=True)
    all_btn.clicked.connect(lambda: _toggle_all_pid_curves(parent))
    cl = _text_btn("Clear", TEXT_DIM, hover=ACCENT_ERR)
    cl.clicked.connect(lambda: _clear_pid_history(parent))
    btn_row.addWidget(ar)
    btn_row.addWidget(all_btn)
    curve_buttons = {}
    for profile_id, color in enumerate(PROFILE_CURVE_COLORS):
        key = f"p{profile_id}"
        btn = _curve_toggle_btn(f"P{profile_id}", color, checked=True, min_width=44)
        btn.clicked.connect(
            lambda checked, k=key: _set_pid_curve_visible(parent, k, checked)
        )
        curve_buttons[key] = btn
        btn_row.addWidget(btn)
    btn_row.addStretch()
    btn_row.addWidget(cl)
    parent._pid_curve_all_btn = all_btn
    parent._pid_curve_buttons = curve_buttons
    lay.addLayout(btn_row)

    grp.setLayout(lay)
    return grp


# ═══════════════════════════════════════════════════════════════════════════════
# C.  PROFILE WIZARD
# Mode tự động: GUI gửi "start stop dur" (3 số), firmware tự chọn mode
# ═══════════════════════════════════════════════════════════════════════════════

def _build_profile_wizard(parent) -> QGroupBox:
    grp = _grp("PROFILE  WIZARD")
    outer = QVBoxLayout()
    outer.setSpacing(10)
    outer.setContentsMargins(10, 10, 10, 10)

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = QHBoxLayout()
    hdr.setSpacing(8)
    hdr.addWidget(_lbl("Profile ID", bold=True))

    parent.wiz_profile_id = _spinbox(0, 7, 0, w=65)
    hdr.addWidget(parent.wiz_profile_id)

    db = _action_btn("Display", ACCENT_CYAN, h=28)
    db.setToolTip("temp_profile_diplay <id>")
    db.clicked.connect(lambda: _cmd_display_profile(parent))
    vb = _action_btn("Validate", ACCENT_WARN, h=28)
    vb.setToolTip("temp_profile_val")
    vb.clicked.connect(lambda: _send(parent, "temp_profile_val"))

    send_btn = _action_btn("SEND PROFILE", ACCENT_TEAL, h=28, bold=True)
    send_btn.setToolTip(
        "Gửi wizard tự động — chờ từng prompt firmware\n"
        "Mode (HEAT/COOL/SOAK) do firmware tự quyết định"
    )
    send_btn.clicked.connect(lambda: _cmd_temperature_profile_set(parent))
    parent._wiz_send_btn = send_btn

    cancel_btn = _action_btn("CANCEL", ACCENT_ERR, h=28, w=90)
    cancel_btn.setVisible(False)
    cancel_btn.clicked.connect(lambda: _cmd_cancel_wizard(parent))
    parent._wiz_cancel_btn = cancel_btn

    hdr.addWidget(db, stretch=1)
    hdr.addWidget(vb, stretch=1)
    hdr.addWidget(send_btn, stretch=1)
    hdr.addWidget(cancel_btn)
    outer.addLayout(hdr)
    outer.addWidget(_hline())

    # ── Profile params ────────────────────────────────────────────────────────
    outer.addWidget(_section_lbl("Profile parameters"))

    pg = QGridLayout()
    pg.setSpacing(6)
    pg.setHorizontalSpacing(12)

    def _ps(row, col, label, attr, lo, hi, default, tip=""):
        pg.addWidget(_lbl(label), row, col * 2)
        sp = _spinbox(lo, hi, default, tip=tip)
        setattr(parent, attr, sp)
        pg.addWidget(sp, row, col * 2 + 1)

    _ps(0, 0, "Main NTC",    "wiz_main_ntc",  0, 7, 0, "0=NTC1…7=NTC8")
    _ps(0, 1, "Sec NTC",     "wiz_sec_ntc",   0, 7, 1, "0=NTC1…7=NTC8")

    pg.addWidget(_lbl("TEC mask"), 1, 0)
    parent.wiz_tec_mask = _spinbox(0, 255, 1, tip="Decimal mask, e.g. 1 = TEC1 on", w=80)
    pg.addWidget(parent.wiz_tec_mask, 1, 1)

    pg.addWidget(_lbl("Heater mask"), 1, 2)
    parent.wiz_heater_mask = _spinbox(0, 255, 2, tip="Decimal mask, e.g. 2 = Heater2 on", w=80)
    pg.addWidget(parent.wiz_heater_mask, 1, 3)

    pg.addWidget(_lbl("Setpoint °C"), 2, 0)
    parent.wiz_setpoint = _dspinbox(-50, 150, 25.0, tip="Firmware nhận *100 tự động")
    pg.addWidget(parent.wiz_setpoint, 2, 1)

    pg.addWidget(_lbl("Delta °C"), 2, 2)
    parent.wiz_delta = _dspinbox(0, 50, 0.0)
    pg.addWidget(parent.wiz_delta, 2, 3)

    outer.addLayout(pg)
    outer.addWidget(_hline())

    # ── Steps ─────────────────────────────────────────────────────────────────
    sc_row = QHBoxLayout()
    sc_row.addWidget(_lbl("Step count", bold=True))
    parent.wiz_step_count = _spinbox(1, MAX_STEPS, 3, w=65)
    parent.wiz_step_count.valueChanged.connect(lambda v: _refresh_step_rows(parent))
    sc_row.addWidget(parent.wiz_step_count)
    sc_row.addStretch()
    outer.addLayout(sc_row)

    # header labels
    hd = QHBoxLayout()
    hd.setContentsMargins(28, 0, 0, 0)
    for txt, stretch in [("start °C", 1), ("stop °C", 1), ("duration  s", 1), ("mode", 1)]:
        l = QLabel(txt)
        l.setStyleSheet(
            f"color:{TEXT_DIM};font-size:10px;font-weight:600;"
            f"letter-spacing:0.5px;background:transparent;"
        )
        l.setAlignment(Qt.AlignCenter)
        hd.addWidget(l, stretch)
    outer.addLayout(hd)

    parent._wiz_step_container = QVBoxLayout()
    parent._wiz_step_container.setSpacing(4)
    parent._wiz_steps = []

    for i in range(MAX_STEPS):
        row_w, widgets = _make_step_row(i)
        parent._wiz_steps.append(widgets)
        parent._wiz_step_container.addWidget(row_w)

    outer.addLayout(parent._wiz_step_container)
    _refresh_step_rows(parent)
    _init_wizard_profile_state(parent)
    outer.addWidget(_hline())

    parent.profile_display_table = _build_profile_display_table()
    outer.addWidget(parent.profile_display_table)

    # ── Status ────────────────────────────────────────────────────────────────
    parent.wiz_status_lbl = QLabel("Idle")
    parent.wiz_status_lbl.setAlignment(Qt.AlignCenter)
    parent.wiz_status_lbl.setStyleSheet(
        f"color:{TEXT_DIM};font-size:11px;font-style:italic;background:transparent;"
    )
    outer.addWidget(parent.wiz_status_lbl)

    grp.setLayout(outer)
    return grp

def _make_step_row(index: int):
    """
    1 hàng step: [idx] start  stop  duration  [MODE badge tự động]
    Mode tự động dựa start vs stop, chỉ hiển thị (không gửi xuống firmware).
    Firmware tự quyết định mode — GUI chỉ gửi "start stop dur".
    """
    widget = QFrame()
    widget.setStyleSheet(
        f"QFrame{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-radius:6px;}}"
    )
    row = QHBoxLayout(widget)
    row.setContentsMargins(8, 4, 8, 4)
    row.setSpacing(8)

    idx_lbl = QLabel(f"[{index}]")
    idx_lbl.setFixedWidth(24)
    idx_lbl.setStyleSheet(
        f"color:{TEXT_DIM};font-size:11px;font-weight:700;"
        f"background:transparent;border:none;"
    )
    row.addWidget(idx_lbl)

    start = _dspinbox(-50, 200, 25.0, compact=True)
    stop  = _dspinbox(-50, 200, 40.0, compact=True)
    dur   = _spinbox2(0, 86400, 60, compact=True)

    # Badge hiển thị mode — tự động theo start/stop
    mode_badge = QLabel("HEAT")
    mode_badge.setFixedWidth(60)
    mode_badge.setAlignment(Qt.AlignCenter)
    mode_badge.setStyleSheet(_mode_badge_style("HEAT"))

    def _update_badge():
        s, e = start.value(), stop.value()
        if e > s:   mode = "HEAT"
        elif e < s: mode = "COOL"
        else:       mode = "SOAK"
        mode_badge.setText(mode)
        mode_badge.setStyleSheet(_mode_badge_style(mode))

    start.valueChanged.connect(lambda _: _update_badge())
    stop.valueChanged.connect(lambda _: _update_badge())
    _update_badge()

    for w in (start, stop, dur):
        row.addWidget(w, stretch=1)
    row.addWidget(mode_badge)

    return widget, (start, stop, dur, mode_badge)


def _mode_badge_style(mode: str) -> str:
    colors = {
        "HEAT": (ACCENT_WARN,  "#3A1800"),
        "COOL": (ACCENT_CYAN,  "#00223A"),
        "SOAK": (ACCENT_TEAL,  "#003020"),
    }
    fg, bg = colors.get(mode, (TEXT_DIM, BG_SURFACE))
    return (
        f"background:{bg};border:1px solid {fg}66;"
        f"border-radius:4px;color:{fg};"
        f"font-size:10px;font-weight:800;letter-spacing:1px;"
        f"padding:2px 4px;"
    )


def _refresh_step_rows(parent):
    n   = parent.wiz_step_count.value()
    lay = parent._wiz_step_container
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item and item.widget():
            item.widget().setVisible(i < n)


def _build_profile_display_table():
    table = QTableWidget(0, 8)
    table.setHorizontalHeaderLabels([
        "ID", "Main", "Sec", "TEC", "Heater", "SP °C", "Delta °C", "Steps"
    ])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.horizontalHeader().setFixedHeight(24)
    table.verticalHeader().setDefaultSectionSize(24)
    table.setFixedHeight(76)
    table.setStyleSheet(_pid_table_style())
    return table


def _default_wizard_profile_snapshot():
    return {
        "main_ntc": 0,
        "sec_ntc": 1,
        "tec_mask": 1,
        "heater_mask": 2,
        "setpoint": 25.0,
        "delta": 0.0,
        "step_count": 3,
        "steps": [
            {"start": 25.0, "stop": 40.0, "duration": 60}
            for _ in range(MAX_STEPS)
        ],
    }


def _ensure_wizard_profile_cache(parent):
    if not hasattr(parent, "_wiz_profile_cache"):
        parent._wiz_profile_cache = {
            pid: _default_wizard_profile_snapshot()
            for pid in range(8)
        }
    return parent._wiz_profile_cache


def _read_wizard_profile_form(parent):
    steps = []
    for start_w, stop_w, dur_w, _ in parent._wiz_steps:
        steps.append({
            "start": float(start_w.value()),
            "stop": float(stop_w.value()),
            "duration": int(dur_w.value()),
        })
    return {
        "main_ntc": int(parent.wiz_main_ntc.value()),
        "sec_ntc": int(parent.wiz_sec_ntc.value()),
        "tec_mask": int(parent.wiz_tec_mask.value()),
        "heater_mask": int(parent.wiz_heater_mask.value()),
        "setpoint": float(parent.wiz_setpoint.value()),
        "delta": float(parent.wiz_delta.value()),
        "step_count": int(parent.wiz_step_count.value()),
        "steps": steps,
    }


def _save_current_wizard_profile(parent):
    if getattr(parent, "_wiz_loading_profile", False):
        return
    cache = _ensure_wizard_profile_cache(parent)
    pid = getattr(parent, "_wiz_current_profile_id", parent.wiz_profile_id.value())
    cache[int(pid)] = _read_wizard_profile_form(parent)


def _apply_wizard_profile_snapshot(parent, snapshot):
    parent._wiz_loading_profile = True
    try:
        parent.wiz_main_ntc.setValue(int(snapshot.get("main_ntc", 0)))
        parent.wiz_sec_ntc.setValue(int(snapshot.get("sec_ntc", 1)))
        parent.wiz_tec_mask.setValue(int(snapshot.get("tec_mask", 1)))
        parent.wiz_heater_mask.setValue(int(snapshot.get("heater_mask", 2)))
        parent.wiz_setpoint.setValue(float(snapshot.get("setpoint", 25.0)))
        parent.wiz_delta.setValue(float(snapshot.get("delta", 0.0)))
        parent.wiz_step_count.setValue(int(snapshot.get("step_count", 3)))

        steps = snapshot.get("steps", [])
        for i, widgets in enumerate(parent._wiz_steps):
            if i >= len(steps):
                break
            start_w, stop_w, dur_w, _ = widgets
            step = steps[i]
            start_w.setValue(float(step.get("start", 25.0)))
            stop_w.setValue(float(step.get("stop", 40.0)))
            dur_w.setValue(int(step.get("duration", 60)))

        _refresh_step_rows(parent)
    finally:
        parent._wiz_loading_profile = False


def _on_wizard_profile_id_changed(parent, new_id):
    if getattr(parent, "_wiz_loading_profile", False):
        return
    cache = _ensure_wizard_profile_cache(parent)
    old_id = getattr(parent, "_wiz_current_profile_id", None)
    if old_id is not None and int(old_id) != int(new_id):
        cache[int(old_id)] = _read_wizard_profile_form(parent)

    parent._wiz_current_profile_id = int(new_id)
    snapshot = cache.get(int(new_id), _default_wizard_profile_snapshot())
    _apply_wizard_profile_snapshot(parent, snapshot)


def _init_wizard_profile_state(parent):
    parent._wiz_loading_profile = False
    parent._wiz_current_profile_id = int(parent.wiz_profile_id.value())
    cache = _ensure_wizard_profile_cache(parent)
    cache[parent._wiz_current_profile_id] = _read_wizard_profile_form(parent)

    for widget in (
        parent.wiz_main_ntc,
        parent.wiz_sec_ntc,
        parent.wiz_tec_mask,
        parent.wiz_heater_mask,
        parent.wiz_setpoint,
        parent.wiz_delta,
        parent.wiz_step_count,
    ):
        widget.valueChanged.connect(lambda *_: _save_current_wizard_profile(parent))

    for start_w, stop_w, dur_w, _ in parent._wiz_steps:
        start_w.valueChanged.connect(lambda *_: _save_current_wizard_profile(parent))
        stop_w.valueChanged.connect(lambda *_: _save_current_wizard_profile(parent))
        dur_w.valueChanged.connect(lambda *_: _save_current_wizard_profile(parent))

    parent.wiz_profile_id.valueChanged.connect(
        lambda v: _on_wizard_profile_id_changed(parent, v)
    )


# ═══════════════════════════════════════════════════════════════════════════════
# D.  PID CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_pid_section(parent) -> QGroupBox:
    grp = _grp("PID  CONSTANTS")
    lay = QVBoxLayout()
    lay.setSpacing(8)
    lay.setContentsMargins(10, 10, 10, 10)

    sr = QHBoxLayout()
    sr.addWidget(_lbl("State ID", bold=True))
    parent.tc_pid_state = _spinbox(1, 8, 1)
    sr.addWidget(parent.tc_pid_state)
    sr.addStretch()
    lay.addLayout(sr)

    pg2 = QGridLayout()
    pg2.setSpacing(6)
    for col, (t, attr) in enumerate([("Kp", "tc_kp"), ("Ki", "tc_ki"), ("Kd", "tc_kd")]):
        l = _lbl(t, bold=True)
        l.setAlignment(Qt.AlignCenter)
        pg2.addWidget(l, 0, col)
        sp = _dspinbox(0, 100, 1.0)
        setattr(parent, attr, sp)
        pg2.addWidget(sp, 1, col)
    lay.addLayout(pg2)

    r = QHBoxLayout()
    r.setSpacing(8)
    g = _action_btn("GET", ACCENT_CYAN)
    s = _action_btn("SET", ACCENT_TEAL)
    g.setToolTip("temp_auto_pid_get <state_id>")
    s.setToolTip("temp_auto_pid_set <state_id> kp ki kd")
    g.clicked.connect(lambda: _cmd_pid_get(parent))
    s.clicked.connect(lambda: _cmd_pid_set(parent))
    r.addWidget(g)
    r.addWidget(s)
    lay.addLayout(r)
    grp.setLayout(lay)
    return grp


# ═══════════════════════════════════════════════════════════════════════════════
# E.  RUN CONTROL
# ═══════════════════════════════════════════════════════════════════════════════

def _build_run_section(parent) -> QGroupBox:
    grp = _grp("RUN  CONTROL")
    lay = QVBoxLayout()
    lay.setSpacing(8)
    lay.setContentsMargins(10, 10, 10, 10)

    rr = QHBoxLayout()
    rr.addWidget(_lbl("Profile ID", bold=True))
    parent.tc_run_profile_id = _spinbox(0, 7, 0)

    parent.wiz_profile_id.valueChanged.connect(
        lambda v: parent.tc_run_profile_id.setValue(v)
    )
    parent.tc_run_profile_id.valueChanged.connect(
        lambda v: parent.wiz_profile_id.setValue(v)
    )
    rr.addWidget(parent.tc_run_profile_id)
    rr.addStretch()
    lay.addLayout(rr)

    r1 = QHBoxLayout()
    r1.setSpacing(8)
    ena = _action_btn("AUTO ENA",    ACCENT_TEAL)
    sta = _action_btn("AUTO START", ACCENT_CYAN)
    ena.setToolTip("temp_auto_ena <id>")
    sta.setToolTip("temp_auto_start <id>")
    ena.clicked.connect(lambda: _cmd_auto_ena(parent))
    sta.clicked.connect(lambda: _cmd_auto_start(parent))
    r1.addWidget(ena)
    r1.addWidget(sta)
    lay.addLayout(r1)

    r2 = QHBoxLayout()
    r2.setSpacing(8)
    mn = _action_btn("STOP",       ACCENT_WARN)
    lg = _action_btn("TOGGLE LOG", ACCENT_PRP)
    mn.setToolTip("temp_manu <id>")
    lg.setToolTip("c — toggle NTC log")
    mn.clicked.connect(lambda: _cmd_manu(parent))
    lg.clicked.connect(lambda: _cmd_toggle_log(parent))
    r2.addWidget(mn)
    r2.addWidget(lg)
    lay.addLayout(r2)

    grp.setLayout(lay)
    return grp


# ═══════════════════════════════════════════════════════════════════════════════
# F.  RESPONSE BOX
# ═══════════════════════════════════════════════════════════════════════════════

def _build_response_box(parent) -> QGroupBox:
    grp = _grp("FIRMWARE  RESPONSE")
    lay = QVBoxLayout()
    lay.setContentsMargins(8, 8, 8, 8)

    parent.tc_response_box = QTextEdit()
    parent.tc_response_box.setReadOnly(True)
    parent.tc_response_box.setFixedHeight(140)
    parent.tc_response_box.setStyleSheet(f"""
        QTextEdit {{
            background-color:{BG_CARD}; border:1px solid {BORDER};
            border-radius:6px; color:{TEXT_SEC};
            font-family:"Cascadia Code","Consolas",monospace;
            font-size:{FONT_BASE}px; padding:6px;
        }}
    """)
    hdr = QHBoxLayout()
    hdr.addStretch()
    cb = _text_btn("Clear", TEXT_DIM, hover=ACCENT_ERR)
    cb.clicked.connect(lambda: parent.tc_response_box.clear())
    hdr.addWidget(cb)
    lay.addLayout(hdr)
    lay.addWidget(parent.tc_response_box)
    grp.setLayout(lay)
    return grp


# ═══════════════════════════════════════════════════════════════════════════════
# REALTIME UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

def update_pid_display(parent):
    import global_var
    try:
        if hasattr(parent, "pid_profile_curves"):
            times_by_profile = getattr(global_var, "pid_profile_time_history", {})
            pv_by_profile = getattr(global_var, "pid_profile_pv_history", {})
            for profile_id, curve in parent.pid_profile_curves.items():
                times = times_by_profile.get(profile_id, [])
                values = pv_by_profile.get(profile_id, [])
                curve.setData(np.array(times), np.array(values))
            _scroll_pid_plot_to_latest(parent)
        elif hasattr(parent, "pid_curve_pv") and len(global_var.pid_pv_history) > 1:
            parent.pid_curve_pv.setData(
                np.array(global_var.pid_time_history),
                np.array(global_var.pid_pv_history)
            )
            _scroll_pid_plot_to_latest(parent)

        _refresh_pid_profile_table(parent)

        # Metric cards
        if hasattr(parent, "pid_card_pv"):
            parent.pid_card_pv.set_value(getattr(global_var, 'pid_pv', 0.0))
        if hasattr(parent, "pid_card_sp"):
            parent.pid_card_sp.set_value(getattr(global_var, 'pid_sp', 0.0))
        if hasattr(parent, "pid_card_err"):
            err = getattr(global_var, 'pid_err', 0.0)
            accent = ACCENT_ERR if abs(err) > 5 else ACCENT_WARN
            parent.pid_card_err.set_value(err, accent_override=accent)
        if hasattr(parent, "pid_card_out"):
            parent.pid_card_out.set_value(getattr(global_var, 'pid_out', 0.0))
        if hasattr(parent, "pid_step_badge"):
            parent.pid_step_badge.set_step(getattr(global_var, 'pid_step', "NONE"))

    except Exception as e:
        print("update_pid_display ERROR:", e)


def _auto_range_pid_plot(parent):
    if hasattr(parent, "_pid_plot_widget"):
        parent._pid_plot_widget.getViewBox().autoRange()
        x_range, _ = parent._pid_plot_widget.getViewBox().viewRange()
        parent._pid_time_window_seconds = max(
            PID_MIN_TIME_WINDOW_SECONDS,
            x_range[1] - x_range[0],
        )
    parent._pid_follow_latest = True


def _pid_wheel_delta(ev):
    if hasattr(ev, "delta"):
        return ev.delta()
    if hasattr(ev, "angleDelta"):
        return ev.angleDelta().y()
    return 0


def _move_pid_measure_cursor(parent, view_box, pos, advance=False):
    cursors = getattr(parent, "_pid_measure_cursors", None)
    if not cursors:
        return

    snap_point = _nearest_pid_curve_point(parent, view_box, pos)
    if snap_point is None:
        return

    cursor_index = _pid_measure_cursor_index(parent, advance=advance)
    cursor = cursors[cursor_index]
    x_value, y_value = snap_point
    cursor["point"] = (x_value, y_value)
    cursor["x_line"].setPos(x_value)
    cursor["y_line"].setPos(y_value)
    cursor["label"].setPos(x_value, y_value)
    cursor["x_line"].show()
    cursor["y_line"].show()
    cursor["label"].show()
    parent._pid_measure_active_index = cursor_index
    _refresh_pid_measure_labels(parent)


def _refresh_pid_measure_labels(parent):
    cursors = getattr(parent, "_pid_measure_cursors", [])
    if not cursors:
        return

    points = [
        cursor.get("point")
        if cursor["label"].isVisible()
        else None
        for cursor in cursors
    ]
    delta_text = ""
    if len(points) >= 2 and points[0] is not None and points[1] is not None:
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
        delta_text = f"\nDelta Time: {dx:+.2f} s\nDelta Temp: {dy:+.2f} C"

    for index, cursor in enumerate(cursors):
        point = cursor.get("point")
        if point is None:
            continue
        extra = delta_text if index == 1 and delta_text else ""
        cursor["label"].setText(
            f"{cursor['name']}\nTime: {point[0]:.2f} s\nTemp: {point[1]:.2f} C{extra}"
        )


def _pid_measure_cursor_index(parent, advance=False):
    cursors = getattr(parent, "_pid_measure_cursors", [])
    if not cursors:
        return 0

    active = getattr(parent, "_pid_measure_active_index", None)
    if not advance and active is not None:
        return active

    for index, cursor in enumerate(cursors):
        if not cursor["label"].isVisible():
            return index

    if active is None:
        return 0
    return (active + 1) % len(cursors)


def _nearest_pid_curve_point(parent, view_box, pos):
    mouse_point = view_box.mapToView(pos)
    x_range, y_range = view_box.viewRange()
    x_span = max(abs(x_range[1] - x_range[0]), PID_MIN_TIME_WINDOW_SECONDS)
    y_span = max(abs(y_range[1] - y_range[0]), PID_MIN_TEMP_WINDOW)
    view_rect = view_box.boundingRect()
    x_pixels = max(view_rect.width(), 1.0)
    y_pixels = max(view_rect.height(), 1.0)
    nearest = None
    nearest_distance = None

    curves = list(getattr(parent, "pid_profile_curves", {}).values())
    fallback_curve = getattr(parent, "pid_curve_pv", None)
    if not curves and fallback_curve is not None:
        curves.append(fallback_curve)

    for curve in curves:
        if not curve.isVisible():
            continue

        x_data, y_data = curve.getData()
        if x_data is None or y_data is None or len(x_data) == 0 or len(y_data) == 0:
            continue

        x_values = np.asarray(x_data, dtype=float)
        y_values = np.asarray(y_data, dtype=float)
        finite = np.isfinite(x_values) & np.isfinite(y_values)
        if not finite.any():
            continue

        x_values = x_values[finite]
        y_values = y_values[finite]
        dx = (x_values - mouse_point.x()) * x_pixels / x_span
        dy = (y_values - mouse_point.y()) * y_pixels / y_span
        distances = dx * dx + dy * dy
        index = int(np.argmin(distances))
        distance = distances[index]
        if nearest_distance is None or distance < nearest_distance:
            nearest = (float(x_values[index]), float(y_values[index]))
            nearest_distance = distance

    return nearest


def _hide_pid_measure_cursor(parent, measure_index=None):
    cursors = getattr(parent, "_pid_measure_cursors", [])
    if measure_index is None:
        indexes = range(len(cursors))
    else:
        indexes = (measure_index,)

    for index in indexes:
        if index < 0 or index >= len(cursors):
            continue
        cursors[index]["point"] = None
        for item in (
            cursors[index]["x_line"],
            cursors[index]["y_line"],
            cursors[index]["label"],
        ):
            item.hide()

    if measure_index == getattr(parent, "_pid_measure_active_index", None):
        parent._pid_measure_active_index = None
    _refresh_pid_measure_labels(parent)


def _wheel_zoom_pid_plot(parent, view_box, ev, zoom_x=True, zoom_y=True):
    delta = _pid_wheel_delta(ev)
    if delta == 0:
        ev.ignore()
        return

    factor = PID_WHEEL_ZOOM_IN_FACTOR if delta > 0 else 1.0 / PID_WHEEL_ZOOM_IN_FACTOR
    try:
        mouse_point = view_box.mapSceneToView(ev.scenePos())
    except Exception:
        x_range, y_range = view_box.viewRange()
        mouse_point = pg.Point(
            (x_range[0] + x_range[1]) / 2.0,
            (y_range[0] + y_range[1]) / 2.0,
        )

    x_range, y_range = view_box.viewRange()

    if zoom_x:
        left = mouse_point.x() - (mouse_point.x() - x_range[0]) * factor
        right = mouse_point.x() + (x_range[1] - mouse_point.x()) * factor
        if right - left < PID_MIN_TIME_WINDOW_SECONDS:
            half = PID_MIN_TIME_WINDOW_SECONDS / 2.0
            left = mouse_point.x() - half
            right = mouse_point.x() + half
        view_box.setXRange(left, right, padding=0)
        parent._pid_time_window_seconds = max(PID_MIN_TIME_WINDOW_SECONDS, right - left)

    if zoom_y:
        bottom = mouse_point.y() - (mouse_point.y() - y_range[0]) * factor
        top = mouse_point.y() + (y_range[1] - mouse_point.y()) * factor
        if top - bottom < PID_MIN_TEMP_WINDOW:
            half = PID_MIN_TEMP_WINDOW / 2.0
            bottom = mouse_point.y() - half
            top = mouse_point.y() + half
        view_box.setYRange(bottom, top, padding=0)

    parent._pid_follow_latest = True
    ev.accept()


def _scroll_pid_plot_to_latest(parent):
    if not getattr(parent, "_pid_follow_latest", True):
        return
    if not hasattr(parent, "_pid_plot_widget"):
        return

    import global_var
    latest = None
    for times in getattr(global_var, "pid_profile_time_history", {}).values():
        if times:
            latest = max(latest or 0.0, times[-1])
    fallback_times = getattr(global_var, "pid_time_history", [])
    if fallback_times:
        latest = max(latest or 0.0, fallback_times[-1])
    if latest is None:
        return

    window = getattr(parent, "_pid_time_window_seconds", PID_TIME_WINDOW_SECONDS)
    window = max(PID_MIN_TIME_WINDOW_SECONDS, window)
    if latest <= window:
        left = 0
        right = max(window, latest + 5)
    else:
        right = latest + 5
        left = right - window
    parent._pid_plot_widget.setXRange(left, right, padding=0)


def _refresh_pid_profile_table(parent):
    if not hasattr(parent, "pid_profile_table_items"):
        return

    import global_var
    latest = getattr(global_var, "pid_profile_latest", {})
    for profile_id, items in parent.pid_profile_table_items.items():
        row = latest.get(
            profile_id,
            {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0},
        )
        items["step"].setText(str(row.get("step", "NONE")))
        items["sp"].setText(f"{row.get('sp', 0.0):+.2f}")
        items["pv"].setText(f"{row.get('pv', 0.0):+.2f}")
        items["err"].setText(f"{row.get('err', 0.0):+.2f}")
        items["out"].setText(f"{row.get('out', 0.0):+.2f}")


# def _clear_pid_history(parent):
#     import global_var
#     for lst in (global_var.pid_pv_history, global_var.pid_sp_history,
#                 global_var.pid_err_history, global_var.pid_target_history):
#         lst.clear()
#     global_var.pid_target_lookup = []
#     if hasattr(parent, "pid_curve_pv"):
#         empty = np.array([], dtype=float)
#         parent.pid_curve_pv.setData(empty, empty)
#         parent.pid_curve_target.setData(empty, empty)

def _clear_pid_history(parent):
    import global_var
    lists = ['pid_pv_history', 'pid_sp_history', 'pid_err_history',
             'pid_time_history', 'pid_target_history', 'pid_target_history_time']
    
    for lst in lists:
        if hasattr(global_var, lst):
            setattr(global_var, lst, [])

    if hasattr(global_var, 'pid_target_profile'):
        global_var.pid_target_profile = []
    if hasattr(global_var, 'pid_start_time'):
        global_var.pid_start_time = None

    # Clear graph
    empty = np.array([], dtype=float)
    profile_history_names = [
        'pid_profile_time_history', 'pid_profile_pv_history',
        'pid_profile_sp_history', 'pid_profile_err_history',
        'pid_profile_out_history',
    ]
    for name in profile_history_names:
        if hasattr(global_var, name):
            setattr(global_var, name, {i: [] for i in range(8)})
    if hasattr(global_var, 'pid_profile_latest'):
        global_var.pid_profile_latest = {
            i: {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0}
            for i in range(8)
        }

    if hasattr(parent, "pid_profile_curves"):
        for curve in parent.pid_profile_curves.values():
            curve.setData(empty, empty)
    if hasattr(parent, "pid_curve_pv"):
        parent.pid_curve_pv.setData(empty, empty)
    if hasattr(parent, "_pid_plot_widget"):
        parent._pid_time_window_seconds = PID_TIME_WINDOW_SECONDS
        parent._pid_follow_latest = True
        parent._pid_plot_widget.setXRange(0, PID_TIME_WINDOW_SECONDS, padding=0)
    _refresh_pid_profile_table(parent)
# ═══════════════════════════════════════════════════════════════════════════════
def _set_pid_curve_visible(parent, curve_key: str, visible: bool):
    curve = getattr(parent, f"pid_curve_{curve_key}", None)
    if curve is not None:
        curve.setVisible(visible)
    _sync_pid_curve_controls(parent)


def _toggle_all_pid_curves(parent):
    buttons = getattr(parent, "_pid_curve_buttons", {})
    show_all = not all(btn.isChecked() for btn in buttons.values())
    for key, btn in buttons.items():
        btn.setChecked(show_all)
        curve = getattr(parent, f"pid_curve_{key}", None)
        if curve is not None:
            curve.setVisible(show_all)
    _sync_pid_curve_controls(parent)


def _sync_pid_curve_controls(parent):
    buttons = getattr(parent, "_pid_curve_buttons", {})
    all_btn = getattr(parent, "_pid_curve_all_btn", None)
    if not buttons or all_btn is None:
        return
    all_visible = all(btn.isChecked() for btn in buttons.values())
    all_btn.setChecked(all_visible)
    all_btn.setText("ALL OFF" if all_visible else "ALL ON")


# TARGET PROFILE BUILDER
#
# Cơ chế 2 bước:
#   1. build_target_profile() khi nhấn START:
#      → tạo lookup table đầy đủ (pid_target_lookup)
#      → reset pid_target_history = []
#
#   2. Mỗi sample PID nhận được, update_pid_display() reveal thêm 1 điểm
#      từ lookup vào pid_target_history
#      → target kéo dài đúng theo thời gian thực, không vẽ sẵn
#
# Hình dạng target (bậc thang):
#   step[0]: stop=30°C, dur=60s  →  [30.0] * 60 samples
#   step[1]: stop=30°C, dur=60s  →  [30.0] * 60 samples
#   step[2]: stop=27°C, dur=60s  →  [27.0] * 60 samples
# ═══════════════════════════════════════════════════════════════════════════════

# def build_target_profile(parent):
#     """
#     Gọi khi nhấn AUTO START.
#     Tạo lookup table, reset history về rỗng.
#     Target sẽ được reveal từng điểm theo sample PV thực tế nhận được.
#     """
#     import global_var

#     global_var.pid_target_history.clear()

#     lookup = []
#     n = parent.wiz_step_count.value()
#     for i in range(n):
#         start_w, stop_w, dur_w, _ = parent._wiz_steps[i]
#         stop_temp = stop_w.value()
#         dur       = max(int(dur_w.value()), 1)
#         lookup.extend([stop_temp] * dur)

#     global_var.pid_target_lookup = lookup

def build_target_profile(parent):
    import global_var
    global_var.pid_target_profile = []
    profile = []
    n = parent.wiz_step_count.value()
    current_time = 0.0

    for i in range(n):
        if i >= len(parent._wiz_steps):
            break
        _, stop_w, dur_w, _ = parent._wiz_steps[i]
        duration = max(float(dur_w.value()), 0.1)
        target_temp = round(stop_w.value(), 2)

        profile.append({
            "t0": current_time,
            "t1": current_time + duration,
            "target": target_temp
        })
        current_time += duration

    global_var.pid_target_profile = profile
    print(f"[DEBUG] Target profile built: {len(profile)} steps, total time {current_time:.1f}s")

# ═══════════════════════════════════════════════════════════════════════════════
# WIZARD BUILD SEQUENCE
# Format step: "start_*100  stop_*100  duration  mode"  (4 số)
# mode: 0=SOAK  1=HEAT  2=COOL  — tự tính từ start/stop
# ═══════════════════════════════════════════════════════════════════════════════

def _build_wizard_seq(parent) -> tuple:
    pid    = parent.wiz_profile_id.value()
    n_step = parent.wiz_step_count.value()

    start_cmd = "temp_profile_set"
    
    # Cấu trúc: (Trigger cụ thể từ Firmware, Phản hồi từ Python)
    seq = [
        ("debug@mcu", ""),
        ("please enter y or n", "y"),
        ("profile index:", str(pid)),
        ("main ntc:", str(parent.wiz_main_ntc.value())),
        ("sec ntc:", str(parent.wiz_sec_ntc.value())),
        ("tec mask:", str(parent.wiz_tec_mask.value())),
        ("heater mask:", str(parent.wiz_heater_mask.value())),
        ("setpoint (0.01*c):", str(int(round(parent.wiz_setpoint.value() * 100)))),
        ("main-sec delta (0.01*c):", str(int(round(parent.wiz_delta.value() * 100)))),
        ("step count:", str(n_step))
    ]

    for i in range(n_step):
        start_w, stop_w, dur_w, _ = parent._wiz_steps[i]
        sv = int(round(start_w.value() * 100))
        ev = int(round(stop_w.value()  * 100))
        dv = int(dur_w.value())

        # Tự tính mode từ start/stop — khớp đúng badge hiển thị trên UI
        s, e = start_w.value(), stop_w.value()
        if e > s:   mv = 1   # HEAT
        elif e < s: mv = 2   # COOL
        else:       mv = 0   # SOAK

        seq.append((f"step[{i}]", f"{sv} {ev} {dv} {mv}"))

    seq.append(("save? (y/n):", "y")) # Lần xác nhận lưu cuối
    return start_cmd, seq


# ═══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

def _cmd_display_profile(parent):
    pid = int(parent.wiz_profile_id.value())
    parent._profile_display_pending_id = pid
    parent._profile_display_pending_at = time.time()
    _send(parent, f"temp_profile_diplay {pid}")
    _parse_profile_display_log_tail(parent, pid)




#####################################################################
def _cmd_temperature_profile_set(parent):
    pid    = parent.wiz_profile_id.value()
    m_ntc  = parent.wiz_main_ntc.value()
    s_ntc  = parent.wiz_sec_ntc.value()
    t_mask = parent.wiz_tec_mask.value()
    h_mask = parent.wiz_heater_mask.value()
    sp     = int(round(parent.wiz_setpoint.value() * 100))
    dt     = int(round(parent.wiz_delta.value() * 100))
    step_count = parent.wiz_step_count.value()

    params = [
        str(pid),
        str(m_ntc),
        str(s_ntc),
        str(t_mask),
        str(h_mask),
        str(sp),
        str(dt),
        str(step_count),
    ]

    for i in range(step_count):
        start_w, stop_w, dur_w, _ = parent._wiz_steps[i]

        start = int(round(start_w.value() * 100))
        stop  = int(round(stop_w.value() * 100))
        dura  = int(dur_w.value())

        if stop > start:
            mode = 1      # HEAT
        elif stop < start:
            mode = 2      # COOL
        else:
            mode = 0      # SOAK

        params.extend([
            str(start),
            str(stop),
            str(dura),
            str(mode),
        ])

    cmd = "temp_prof_set " + " ".join(params)

    _send(parent, cmd)
    _log_resp(parent, f"[UI] Profile SET → ID {pid}")







def _cmd_send_wizard(parent):
    if parent._wizard_sm and parent._wizard_sm.is_active():
        _log_resp(parent, "[WIZ] Already running — click CANCEL first")
        return

    if hasattr(parent, "pause_bmp390_for_temp_auto"):
        parent.pause_bmp390_for_temp_auto()

    start_cmd, seq = _build_wizard_seq(parent)
    _log_resp(parent, f"[WIZ] Sequence initialized ({len(seq)} steps).")
    for i, (trig, resp) in enumerate(seq):
        _log_resp(parent, f"  [{i}] Wait for '{trig}' → Send '{resp}'")

    sm = WizardStateMachine(parent, start_cmd, seq)
    parent._wizard_sm = sm
    sm.finished.connect(lambda ok, msg: _on_wizard_finished(parent, ok, msg))

    parent._wiz_send_btn.setEnabled(False)
    parent._wiz_cancel_btn.setVisible(True)
    parent.wiz_status_lbl.setText("⏳  Wizard running…")
    parent.wiz_status_lbl.setStyleSheet(
        f"color:{ACCENT_WARN};font-size:11px;font-style:italic;background:transparent;"
    )
    sm.start()


def _cmd_cancel_wizard(parent):
    if parent._wizard_sm:
        parent._wizard_sm.cancel()
    _on_wizard_finished(parent, False, "Cancelled by user")


def _on_wizard_finished(parent, ok, msg):
    parent._wiz_send_btn.setEnabled(True)
    parent._wiz_cancel_btn.setVisible(False)
    color = ACCENT_TEAL if ok else ACCENT_ERR
    icon  = "✓" if ok else "✗"
    parent.wiz_status_lbl.setText(f"{icon}  {msg}")
    parent.wiz_status_lbl.setStyleSheet(
        f"color:{color};font-size:11px;font-style:italic;background:transparent;"
    )


def _cmd_pid_get(parent):
    _send(parent, f"temp_auto_pid_get {parent.tc_pid_state.value()}")


def _cmd_pid_set(parent):
    sid = parent.tc_pid_state.value()
    _send(parent,
          f"temp_auto_pid_set {sid} "
          f"{parent.tc_kp.value():.2f} "
          f"{parent.tc_ki.value():.2f} "
          f"{parent.tc_kd.value():.2f}")


def _cmd_auto_ena(parent):
    import global_var
    pid = parent.tc_run_profile_id.value()

    _clear_pid_history(parent)
    global_var.pid_graph_session_active = True
    global_var.pid_start_time = time.time()
    if hasattr(parent, "pause_bmp390_for_temp_auto"):
        parent.pause_bmp390_for_temp_auto()

    _send(parent, f"temp_auto_ena {pid}")
    _log_resp(parent, f"[UI] Auto ENA → profile {pid}")


# def _cmd_auto_start(parent):
#     pid = parent.tc_run_profile_id.value()
#     _send(parent, f"temp_auto_start {pid}")
#     build_target_profile(parent)   # vẽ đường target
#     _log_resp(parent, f"[UI] Auto START → profile {pid}")

def _cmd_auto_start(parent):
    import global_var
    pid = parent.tc_run_profile_id.value()

    # If the user starts directly from AUTO START, make sure the graph session
    # is armed as well. AUTO ENA already does this path before START.
    if not getattr(global_var, "pid_graph_session_active", False):
        _clear_pid_history(parent)
        global_var.pid_graph_session_active = True
        global_var.pid_start_time = time.time()
        if hasattr(parent, "pause_bmp390_for_temp_auto"):
            parent.pause_bmp390_for_temp_auto()

    build_target_profile(parent)

    _send(parent, f"temp_auto_start {pid}")
    _log_resp(parent, f"[UI] Auto START → profile {pid}")


def _cmd_manu(parent):
    import global_var
    pid = parent.tc_run_profile_id.value()
    global_var.pid_graph_session_active = False
    _send(parent, f"temp_manu {pid}")
    if hasattr(parent, "resume_bmp390_after_temp_auto"):
        parent.resume_bmp390_after_temp_auto()
    _log_resp(parent, f"[UI] Manual → profile {pid}")


def _cmd_toggle_log(parent):
    _send(parent, "c")
    _log_resp(parent, "[UI] Toggle NTC log")


# ═══════════════════════════════════════════════════════════════════════════════
# UART HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def apply_cli_temp_side_effects(parent, cmd: str):
    text = str(cmd or "").strip()
    if not text:
        return

    parts = text.split()
    name = parts[0].lower() if parts else ""
    if name not in {"temp_auto_ena", "temp_auto_start", "temp_manu"}:
        return

    pid = None
    if len(parts) >= 2:
        try:
            parsed = int(parts[1], 10)
            if 0 <= parsed <= 7:
                pid = parsed
        except Exception:
            pid = None

    if pid is not None and hasattr(parent, "tc_run_profile_id"):
        parent.tc_run_profile_id.setValue(pid)

    if name == "temp_auto_ena":
        import global_var
        _clear_pid_history(parent)
        global_var.pid_graph_session_active = True
        global_var.pid_start_time = time.time()
        if hasattr(parent, "pause_bmp390_for_temp_auto"):
            parent.pause_bmp390_for_temp_auto()
        return

    if name == "temp_auto_start":
        import global_var
        if not getattr(global_var, "pid_graph_session_active", False):
            _clear_pid_history(parent)
            global_var.pid_graph_session_active = True
            global_var.pid_start_time = time.time()
            if hasattr(parent, "pause_bmp390_for_temp_auto"):
                parent.pause_bmp390_for_temp_auto()
        build_target_profile(parent)
        return

    if name == "temp_manu":
        import global_var
        global_var.pid_graph_session_active = False
        if hasattr(parent, "resume_bmp390_after_temp_auto"):
            parent.resume_bmp390_after_temp_auto()


def _send(parent, cmd: str):
    _log_resp(parent, f"→ {cmd}")
    if hasattr(parent, "uart") and parent.uart:
        parent.uart.send_command(cmd)
    else:
        _log_resp(parent, "  [ERR] Not connected")


def _log_resp(parent, msg: str):
    if hasattr(parent, "tc_response_box"):
        parent.tc_response_box.append(msg)
    # Chuyển tiếp log sang terminal MCU chính để người dùng dễ theo dõi tiến độ Wizard
    if hasattr(parent, "_append_ttys2_log"):
        parent._append_ttys2_log(f"[WIZARD] {msg}")


def _profile_display_cache(parent):
    if not hasattr(parent, "_profile_display_cache"):
        parent._profile_display_cache = {}
    return parent._profile_display_cache


def _clean_profile_display_line(line: str) -> str:
    text = str(line or "").strip()
    text = re.sub(r"^\[[^\]]+\]\s*", "", text)
    text = text.lstrip("→").strip()
    return text


def _profile_id_from_line(line: str, fallback=None):
    patterns = (
        r"\bprofile\s*\[\s*(\d+)\s*\]",
        r"\bprofile[_\s-]*(?:id|index)\s*[:=#]?\s*(\d+)",
        r"\bprofile\s*(?:id|index)?\s*[:=#]?\s*(\d+)",
    )
    for pattern in patterns:
        m = re.search(pattern, line, re.IGNORECASE)
        if m:
            pid = int(m.group(1))
            if 0 <= pid <= 7:
                return pid
    return fallback


def _profile_temp_value(raw, line: str):
    value = float(raw)
    if abs(value) > 200 or "0.01" in line.lower():
        value /= 100.0
    return value


def _profile_mode_name(raw):
    text = str(raw).strip().upper()
    return {"0": "SOAK", "1": "HEAT", "2": "COOL"}.get(text, text)


def _ensure_profile_display(parent, pid):
    cache = _profile_display_cache(parent)
    return cache.setdefault(pid, {
        "id": pid,
        "main_ntc": None,
        "sec_ntc": None,
        "tec_mask": None,
        "heater_mask": None,
        "setpoint": None,
        "delta": None,
        "step_count": None,
        "steps": {},
    })


def _set_profile_field(profile, key, value):
    if profile.get(key) == value:
        return False
    profile[key] = value
    return True


def _extract_profile_fields(line: str, profile: dict) -> bool:
    changed = False
    int_fields = {
        "main_ntc": (
            r"\bmain(?:[_\s-]*ntc)?\b\s*[:=]\s*(-?\d+)",
            r"\bmain[_\s-]*ntc\b[^\d+-]*(-?\d+)",
        ),
        "sec_ntc": (
            r"\bsec(?:ondary)?(?:[_\s-]*ntc)?\b\s*[:=]\s*(-?\d+)",
            r"\bsec[_\s-]*ntc\b[^\d+-]*(-?\d+)",
        ),
        "tec_mask": (
            r"\btec(?:[_\s-]*mask)?\b\s*[:=]\s*(-?\d+)",
            r"\btec[_\s-]*mask\b[^\d+-]*(-?\d+)",
        ),
        "heater_mask": (
            r"\bheater(?:[_\s-]*mask)?\b\s*[:=]\s*(-?\d+)",
            r"\bheater[_\s-]*mask\b[^\d+-]*(-?\d+)",
        ),
        "step_count": (
            r"\bstep[_\s-]*count\b[^\d+-]*(-?\d+)",
            r"\bsteps\b[^\d+-]*(-?\d+)",
        ),
    }
    for key, patterns in int_fields.items():
        for pattern in patterns:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                changed |= _set_profile_field(profile, key, int(m.group(1)))
                break

    float_fields = {
        "setpoint": (
            r"\bset\s*point\b[^\d+-]*([+-]?\d+(?:\.\d+)?)",
            r"\bsetpoint\b[^\d+-]*([+-]?\d+(?:\.\d+)?)",
        ),
        "delta": (
            r"\b(?:main\s*-\s*sec\s*)?delta\b[^\d+-]*([+-]?\d+(?:\.\d+)?)",
        ),
    }
    for key, patterns in float_fields.items():
        for pattern in patterns:
            m = re.search(pattern, line, re.IGNORECASE)
            if m:
                changed |= _set_profile_field(
                    profile,
                    key,
                    _profile_temp_value(m.group(1), line),
                )
                break
    return changed


def _extract_profile_step(line: str, profile: dict) -> bool:
    m = re.search(r"\bstep\s*\[?\s*(\d+)\s*\]?\s*[:=]?\s*(.*)$", line, re.IGNORECASE)
    if not m:
        return False

    step_idx = int(m.group(1))
    rest = m.group(2)
    if not 0 <= step_idx < MAX_STEPS:
        return False

    named = {}
    for key, pattern in {
        "start": r"\bstart\b[^\d+-]*([+-]?\d+(?:\.\d+)?)",
        "stop": r"\b(?:stop|end)\b[^\d+-]*([+-]?\d+(?:\.\d+)?)",
        "duration": r"\b(?:duration|dur)\b[^\d+-]*(\d+)",
        "mode": r"\bmode\b[^\w+-]*([A-Za-z]+|\d+)",
    }.items():
        match = re.search(pattern, rest, re.IGNORECASE)
        if match:
            named[key] = match.group(1)

    if {"start", "stop", "duration"}.issubset(named):
        start = _profile_temp_value(named["start"], line)
        stop = _profile_temp_value(named["stop"], line)
        duration = int(float(named["duration"]))
        mode = _profile_mode_name(named.get("mode", ""))
    else:
        nums = re.findall(r"[+-]?\d+(?:\.\d+)?", rest)
        if len(nums) < 3:
            return False
        start = _profile_temp_value(nums[0], line)
        stop = _profile_temp_value(nums[1], line)
        duration = int(float(nums[2]))
        mode = _profile_mode_name(nums[3]) if len(nums) > 3 else ""

    step = {
        "start": start,
        "stop": stop,
        "duration": duration,
        "mode": mode,
    }
    if profile["steps"].get(step_idx) == step:
        return False
    profile["steps"][step_idx] = step
    return True


def _extract_compact_profile_line(parent, line: str, profile: dict) -> bool:
    pending_at = getattr(parent, "_profile_display_pending_at", 0)
    if time.time() - pending_at > 15:
        return False
    if "pid:" in line.lower() or line.upper().startswith("STEP="):
        return False

    nums = re.findall(r"[+-]?\d+(?:\.\d+)?", line)
    if len(nums) < 7:
        return False

    offset = 0
    maybe_pid = int(float(nums[0]))
    if 0 <= maybe_pid <= 7 and len(nums) >= 8:
        offset = 1

    values = nums[offset:offset + 7]
    changed = False
    changed |= _set_profile_field(profile, "main_ntc", int(float(values[0])))
    changed |= _set_profile_field(profile, "sec_ntc", int(float(values[1])))
    changed |= _set_profile_field(profile, "tec_mask", int(float(values[2])))
    changed |= _set_profile_field(profile, "heater_mask", int(float(values[3])))
    changed |= _set_profile_field(profile, "setpoint", _profile_temp_value(values[4], line))
    changed |= _set_profile_field(profile, "delta", _profile_temp_value(values[5], line))
    changed |= _set_profile_field(profile, "step_count", int(float(values[6])))
    return changed


def _merge_display_profile_into_form_cache(parent, profile: dict):
    pid = int(profile["id"])
    cache = _ensure_wizard_profile_cache(parent)
    snapshot = cache.get(pid, _default_wizard_profile_snapshot())

    for source, target in (
        ("main_ntc", "main_ntc"),
        ("sec_ntc", "sec_ntc"),
        ("tec_mask", "tec_mask"),
        ("heater_mask", "heater_mask"),
        ("setpoint", "setpoint"),
        ("delta", "delta"),
        ("step_count", "step_count"),
    ):
        if profile.get(source) is not None:
            snapshot[target] = profile[source]

    steps = snapshot.setdefault("steps", _default_wizard_profile_snapshot()["steps"])
    for idx, step in profile.get("steps", {}).items():
        if idx < len(steps):
            steps[idx] = {
                "start": float(step.get("start", 25.0)),
                "stop": float(step.get("stop", 40.0)),
                "duration": int(step.get("duration", 60)),
            }

    cache[pid] = snapshot
    if getattr(parent, "_wiz_current_profile_id", None) == pid:
        _apply_wizard_profile_snapshot(parent, snapshot)


def _fmt_profile_value(value):
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _step_mode_short(mode):
    return {"HEAT": "H", "COOL": "C", "SOAK": "S"}.get(str(mode).upper(), "")


def _profile_steps_summary(profile):
    steps = profile.get("steps", {})
    count = profile.get("step_count")
    if not steps:
        return f"{count} step" if count is not None else "--"

    parts = []
    for idx in sorted(steps):
        step = steps[idx]
        parts.append(
            f"{idx}:{_fmt_profile_value(step.get('start'))}"
            f"->{_fmt_profile_value(step.get('stop'))}"
            f"/{step.get('duration', '--')}s"
            f"{_step_mode_short(step.get('mode'))}"
        )
    prefix = f"{count} | " if count is not None else ""
    return prefix + "; ".join(parts)


def _refresh_profile_display_table(parent):
    table = getattr(parent, "profile_display_table", None)
    if table is None:
        return

    cache = _profile_display_cache(parent)
    table.setRowCount(0)
    for row, pid in enumerate(sorted(cache)):
        profile = cache[pid]
        table.insertRow(row)
        values = [
            pid,
            profile.get("main_ntc"),
            profile.get("sec_ntc"),
            profile.get("tec_mask"),
            profile.get("heater_mask"),
            profile.get("setpoint"),
            profile.get("delta"),
            _profile_steps_summary(profile),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(_fmt_profile_value(value))
            item.setTextAlignment(Qt.AlignCenter if col < 7 else Qt.AlignLeft | Qt.AlignVCenter)
            table.setItem(row, col, item)


def _capture_profile_display_line(parent, line: str, force_pid=None):
    text = _clean_profile_display_line(line)
    if not text:
        return

    pending_id = getattr(parent, "_profile_display_pending_id", None)
    pid = _profile_id_from_line(text, force_pid if force_pid is not None else pending_id)
    if pid is None:
        return

    profile = _ensure_profile_display(parent, int(pid))
    changed = False
    changed |= _extract_profile_fields(text, profile)
    changed |= _extract_profile_step(text, profile)
    if not changed:
        changed |= _extract_compact_profile_line(parent, text, profile)

    if changed:
        _merge_display_profile_into_form_cache(parent, profile)
        _refresh_profile_display_table(parent)


def _parse_profile_display_log_tail(parent, pid):
    box = getattr(parent, "tc_response_box", None)
    if box is None:
        return
    lines = box.toPlainText().splitlines()[-120:]
    start = len(lines)
    command_re = re.compile(rf"\btemp_profile_diplay\s+{int(pid)}\b", re.IGNORECASE)
    for idx in range(len(lines) - 1, -1, -1):
        if command_re.search(lines[idx]):
            start = idx + 1
            break
    for line in lines[start:]:
        _capture_profile_display_line(parent, line, force_pid=pid)


def pipe_to_response(parent, line: str):
    """Pipe UART line → response box + feed wizard. Gọi từ protocol_parser."""
    if hasattr(parent, "tc_response_box"):
        parent.tc_response_box.append(f"  {line}")
    _capture_profile_display_line(parent, line)
    if hasattr(parent, "_wizard_sm") and parent._wizard_sm:
        parent._wizard_sm.feed_line(line)


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class _StepBadge(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(42)
        self.set_step("NONE")

    def set_step(self, step: str):
        su  = step.upper().split(":")[0]
        bg, fg = STEP_COLORS.get(su, STEP_COLORS["NONE"])
        sym = {"HEAT": "▲", "COOL": "▼", "SOAK": "◆"}.get(su, "·")
        self.setText(f"  {sym}    STEP :  {step.upper()}    {sym}  ")
        self.setStyleSheet(f"""
            QLabel {{
                background-color:{bg}; border:1.5px solid {fg}66;
                border-radius:8px; color:{fg};
                font-family:"Cascadia Code","Consolas",monospace;
                font-size:15px; font-weight:800; letter-spacing:3px;
            }}
        """)


class _MetricCard(QFrame):
    def __init__(self, label: str, unit: str, accent: str):
        super().__init__()
        self._accent = accent
        self._unit   = unit
        self.setStyleSheet(f"""
            QFrame {{
                background-color:{BG_CARD}; border:1.5px solid {BORDER};
                border-radius:10px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(78)

        lay = QVBoxLayout(self)
        lay.setSpacing(2)
        lay.setContentsMargins(8, 6, 8, 6)

        self._lbl_w = QLabel(label)
        self._lbl_w.setAlignment(Qt.AlignCenter)
        self._lbl_w.setStyleSheet(
            f"color:{TEXT_DIM};font-size:11px;font-weight:700;"
            f"letter-spacing:1.5px;background:transparent;border:none;"
        )
        self._val_w = QLabel("—")
        self._val_w.setAlignment(Qt.AlignCenter)
        self._val_w.setStyleSheet(
            f"color:{accent};font-size:20px;font-weight:800;"
            f"background:transparent;border:none;"
        )
        lay.addWidget(self._lbl_w)
        lay.addWidget(self._val_w)

    def set_value(self, value: float, accent_override: str = None):
        accent = accent_override or self._accent
        self._val_w.setText(f"{value:+.2f} {self._unit}")
        self._val_w.setStyleSheet(
            f"color:{accent};font-size:20px;font-weight:800;"
            f"background:transparent;border:none;"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# STYLE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _grp(title: str) -> QGroupBox:
    g = QGroupBox(title)
    g.setStyleSheet(f"""
        QGroupBox {{
            background-color:{BG_SURFACE}; border:1.5px solid {BORDER};
            border-radius:10px; margin-top:22px;
            padding:8px 8px 8px 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin:margin; subcontrol-position:top left;
            left:12px; top:3px;
            color:{ACCENT_CYAN}; font-size:{FONT_BASE + 1}px; font-weight:800;
            letter-spacing:0px;
        }}
    """)
    return g


def _pid_table_style():
    return f"""
        QTableWidget {{
            background:{BG_CARD};
            border:1.5px solid {BORDER};
            border-radius:8px;
            color:{TEXT_SEC};
            gridline-color:{BORDER};
            font-size:12px;
            font-weight:700;
        }}
        QHeaderView::section {{
            background:{BG_SURFACE};
            border:none;
            border-right:1px solid {BORDER};
            border-bottom:1px solid {BORDER};
            color:{ACCENT_CYAN};
            font-size:12px;
            font-weight:800;
            padding:4px;
        }}
        QTableWidget::item {{
            border:none;
            padding:3px 6px;
        }}
    """


def _action_btn(label, accent, h=34, w=None, bold=False):
    b = QPushButton(label)
    b.setFixedHeight(h)
    if w:
        b.setFixedWidth(w)
    else:
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    fw = "800" if bold else "700"
    bg = _rgba(accent, 0.22)
    bg_hover = _rgba(accent, 0.34)
    bg_pressed = _rgba(accent, 0.14)
    bg_disabled = _rgba(accent, 0.08)
    hover_border = TEXT_PRIM
    b.setStyleSheet(f"""
        QPushButton{{
            background-color:{bg};
            border:2px solid {accent};
            border-radius:7px;color:{TEXT_PRIM};
            font-size:13px;font-weight:{fw};letter-spacing:0.4px;
        }}
        QPushButton:hover{{
            background-color:{bg_hover};
            border:2px solid {hover_border};
        }}
        QPushButton:pressed{{
            background-color:{bg_pressed};
            border:2px solid {accent};
        }}
        QPushButton:disabled{{
            background-color:{bg_disabled};
            border:2px solid {BORDER};
            color:{TEXT_DIM};}}
    """)
    return b


def _text_btn(label, color, hover):
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setStyleSheet(
        f"QPushButton{{background:transparent;border:1.5px solid {BORDER};"
        f"border-radius:5px;color:{color};font-size:12px;font-weight:600;"
        f"padding:2px 8px;}}"
        f"QPushButton:hover{{color:{hover};border-color:{hover};}}"
    )
    return b


def _curve_toggle_btn(label, accent, checked=True, min_width=82):
    b = QPushButton(label)
    b.setCheckable(True)
    b.setChecked(checked)
    b.setFixedHeight(26)
    b.setMinimumWidth(min_width)
    bg_checked = _rgba(accent, 0.22)
    bg_hover = _rgba(accent, 0.34)
    bg_unchecked = _rgba(accent, 0.06)
    b.setStyleSheet(f"""
        QPushButton{{
            background:{bg_unchecked};
            border:1.5px solid {BORDER};
            border-radius:5px;
            color:{TEXT_DIM};
            font-size:12px;
            font-weight:700;
            padding:2px 10px;
        }}
        QPushButton:checked{{
            background:{bg_checked};
            border-color:{accent};
            color:{TEXT_PRIM};
        }}
        QPushButton:hover{{
            background:{bg_hover};
            border-color:{accent};
            color:{TEXT_PRIM};
        }}
    """)
    return b


def _icon_btn(icon, accent):
    b = QPushButton(icon)
    b.setFixedSize(34, 34)
    b.setStyleSheet(f"""
        QPushButton{{background-color:{BG_CARD};border:1.5px solid {BORDER};
            border-radius:6px;color:{accent};font-size:16px;font-weight:800;}}
        QPushButton:hover{{background-color:{BG_SURFACE};border-color:{accent};}}
    """)
    return b


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


# def _lbl(text, bold=False):
#     l = QLabel(text)
#     fw = "700" if bold else "500"
#     l.setStyleSheet(
#         f"color:{TEXT_SEC};font-size:12px;font-weight:{fw};"
#         f"background:transparent;"
#     )
#     return l

def _lbl(text, bold=False):
    l = QLabel(text)
    fw = "700" if bold else "500"
    l.setStyleSheet(
        f"color:{TEXT_SEC}; font-size:{FONT_BASE}px; font-weight:{fw};"
        f"background:transparent;"
    )
    return l


# def _section_lbl(text):
#     l = QLabel(text)
#     l.setStyleSheet(
#         f"color:{ACCENT_CYAN};font-size:11px;font-weight:700;"
#         f"letter-spacing:1px;background:transparent;"
#     )
#     return l

def _section_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{ACCENT_CYAN}; font-size:{FONT_BASE + 1}px; font-weight:700;"
        f"letter-spacing:1px; background:transparent;"
    )
    return l


def _hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background:{BORDER};max-height:1px;border:none;")
    return f


def _spinbox(lo, hi, default, tip="", w=None):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(default)
    s.setFixedHeight(34)
    if w:
        s.setFixedWidth(w)
    if tip:
        s.setToolTip(tip)
    s.setStyleSheet(_sb_style())
    return s


def _spinbox2(lo, hi, default, compact=False):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(default)
    s.setFixedHeight(30 if compact else 34)
    s.setStyleSheet(_sb_style(compact))
    return s


def _dspinbox(lo, hi, default, tip="", compact=False):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setValue(default)
    s.setDecimals(2)
    s.setSingleStep(1.0)
    s.setFixedHeight(30 if compact else 34)
    if tip:
        s.setToolTip(tip)
    s.setStyleSheet(_sb_style(compact))
    return s


def _lineedit(default, tip="", w=None):
    e = QLineEdit(default)
    if tip:
        e.setToolTip(tip)
    e.setFixedHeight(34)
    if w:
        e.setFixedWidth(w)
    e.setStyleSheet(_input_style())
    return e


def _sb_style(compact=False):
    fs = f"{FONT_BASE - 1}px" if compact else f"{FONT_BASE}px"
    return f"""
        QSpinBox,QDoubleSpinBox{{
            background:{BG_CARD};border:1.5px solid {BORDER};
            border-radius:6px;color:{TEXT_PRIM};
            font-size:{fs};font-weight:700;padding:3px 8px;
        }}
        QSpinBox:focus,QDoubleSpinBox:focus{{border-color:{ACCENT_CYAN};}}
        QSpinBox::up-button,QDoubleSpinBox::up-button,
        QSpinBox::down-button,QDoubleSpinBox::down-button{{
            width:16px;border:none;background:transparent;
        }}
    """


def _input_style():
    return f"""
        QLineEdit{{
            background:{BG_CARD};border:1.5px solid {BORDER};
            border-radius:6px;color:{TEXT_PRIM};
            font-family:"Cascadia Code","Consolas",monospace;
            font-size:13px;font-weight:700;padding:3px 10px;
        }}
        QLineEdit:focus{{border-color:{ACCENT_CYAN};}}
    """
