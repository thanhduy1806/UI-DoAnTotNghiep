from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QTabWidget,
    QGridLayout, QFrame, QLabel, QPushButton
)
from PyQt5.QtCore import QTimer

import pyqtgraph as pg

# GLOBAL
import global_var

# UART + Parser
from uart_ui import apply_uart_theme, create_uart_group_box
from protocol_parser import parse_uart_line

# Sensors
from bmp390 import apply_on_board_condition_theme, create_on_board_condition_strip
from theme import app_stylesheet, current_theme_name, get_theme
from theme import outline_button_style, toggle_theme

# TEMP SYSTEM
from temp_ctrl import (
    apply_temp_ctrl_theme,
    create_temp_ctrl_tab,
    update_pid_display,
    pipe_to_response
)

from exp_manual import create_manual_group_box
from exp_manual import apply_manual_theme
from exp_auto import create_auto_group_box


# ─── COLOR PALETTE ─────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════
# MAIN WINDOW
# ═══════════════════════════════════════════════════════════════

class CubeSatMonitor(QWidget):

    def __init__(self):
        super().__init__()

        # IMPORTANT
        global_var.window = self

        self.setWindowTitle("CubeSat Ground Station")
        self.resize(1600, 900)
        self.setStyleSheet(app_stylesheet())
        self._log_panel_visible = True

        root = QVBoxLayout(self)

        # ── HEADER ───────────────────────────────────────────
        top = QHBoxLayout()

        self.title_label = QLabel("MISSION CONTROL")

        top.addWidget(self.title_label)
        top.addStretch()

        self.theme_btn = QPushButton()
        self.theme_btn.setFixedWidth(120)
        self.theme_btn.clicked.connect(self._toggle_theme)
        top.addWidget(self.theme_btn)

        self.log_panel_btn = QPushButton("HIDE LOG")
        self.log_panel_btn.setFixedWidth(110)
        self.log_panel_btn.clicked.connect(self._toggle_log_panel)
        top.addWidget(self.log_panel_btn)

        root.addLayout(top)

        # ── MAIN GRID ───────────────────────────────────────
        self.main_grid = QGridLayout()
        root.addLayout(self.main_grid)

        self.left_panel   = self._build_left()
        self.center_panel = self._build_center()
        self.right_panel  = self._build_right()

        self.main_grid.addWidget(self.left_panel,   0, 0)
        self.main_grid.addWidget(self.center_panel, 0, 1)
        self.main_grid.addWidget(self.right_panel,  0, 2)

        self._apply_panel_layout()

        # ── TIMER ───────────────────────────────────────────
        self.timer = QTimer()

        self.timer.timeout.connect(
            lambda: self._safe_pid_update()
        )

        self.timer.start(1000)

        self.bmp390_timer = QTimer()
        self.bmp390_timer.timeout.connect(self._poll_bmp390)
        self.bmp390_timer.start(10000)

        self._apply_theme()
    
        # ═══════════════════════════════════════════════════════
    # SAFE LOG APPEND
    # ═══════════════════════════════════════════════════════

    def _append_log(self, text):

        try:

            if not hasattr(self, "log_box"):
                return

            self.log_box.append(text)

            # chỉ giữ 200 dòng gần nhất
            doc = self.log_box.document()

            MAX_LINES = 200

            while doc.blockCount() > MAX_LINES:

                cursor = self.log_box.textCursor()

                cursor.movePosition(cursor.Start)
                cursor.select(cursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

        except Exception as e:

            print("log append error:", e)

    # ═══════════════════════════════════════════════════════
    # SAFE PID UPDATE
    # ═══════════════════════════════════════════════════════

    def _safe_pid_update(self):

        try:
            update_pid_display(self)

        except Exception as e:
            print("PID update error:", e)

    def _poll_bmp390(self):
        try:
            if not hasattr(self, "uart") or not self.uart:
                return
            if not getattr(self.uart, "ser", None):
                return

            self.uart.send_command("bmp390_int_read")

        except Exception as e:
            print("BMP390 poll error:", e)

    def _toggle_theme(self):
        toggle_theme()
        apply_temp_ctrl_theme()
        self._rebuild_temp_ctrl_tab()
        self._apply_theme()

    def _apply_theme(self):
        t = get_theme()
        self.setStyleSheet(app_stylesheet())
        self.title_label.setStyleSheet(f"""
            font-size: 18px;
            color: {t["accent_cyan"]};
            font-weight: bold;
        """)

        next_mode = "LIGHT" if current_theme_name() == "dark" else "DARK"
        self.theme_btn.setText(f"{next_mode} THEME")
        self.theme_btn.setStyleSheet(outline_button_style(t["accent_cyan"]))
        self.log_panel_btn.setStyleSheet(outline_button_style(t["accent_cyan"]))

        apply_on_board_condition_theme(self)
        apply_uart_theme(self)
        apply_manual_theme(self)

    def _rebuild_temp_ctrl_tab(self):
        if not hasattr(self, "center_layout"):
            return

        old = getattr(self, "temp_ctrl_tab", None)
        if old is not None:
            self.center_layout.removeWidget(old)
            old.setParent(None)
            old.deleteLater()

        self.temp_ctrl_tab = create_temp_ctrl_tab(self)
        self.center_layout.addWidget(self.temp_ctrl_tab)

    def _toggle_log_panel(self):
        self._log_panel_visible = not self._log_panel_visible
        self.left_panel.setVisible(self._log_panel_visible)
        self.log_panel_btn.setText(
            "HIDE LOG" if self._log_panel_visible else "SHOW LOG"
        )
        self._apply_panel_layout()

    def _apply_panel_layout(self):
        if self._log_panel_visible:
            self.main_grid.setColumnStretch(0, 2)
            self.main_grid.setColumnStretch(1, 5)
            self.main_grid.setColumnStretch(2, 2)
            self.main_grid.setColumnMinimumWidth(0, 280)
        else:
            self.main_grid.setColumnStretch(0, 0)
            self.main_grid.setColumnStretch(1, 7)
            self.main_grid.setColumnStretch(2, 2)
            self.main_grid.setColumnMinimumWidth(0, 0)

    # ═══════════════════════════════════════════════════════
    # LEFT
    # ═══════════════════════════════════════════════════════

    def _build_left(self):

        box = QFrame()
        lay = QVBoxLayout(box)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        lay.addWidget(self.log_box)

        return box

    # ═══════════════════════════════════════════════════════
    # CENTER
    # ═══════════════════════════════════════════════════════

    def _build_center(self):

        box = QFrame()
        self.center_layout = QVBoxLayout(box)
        self.center_layout.setSpacing(8)

        self.on_board_condition = create_on_board_condition_strip(self)
        self.temp_ctrl_tab = create_temp_ctrl_tab(self)

        self.center_layout.addWidget(self.on_board_condition)
        self.center_layout.addWidget(self.temp_ctrl_tab)

        return box

    # ═══════════════════════════════════════════════════════
    # RIGHT
    # ═══════════════════════════════════════════════════════

    def _build_right(self):

        box = QFrame()
        lay = QVBoxLayout(box)

        self.tabs = QTabWidget()

        self.manual_box = create_manual_group_box(self)
        self.auto_box   = create_auto_group_box(self)

        self.tabs.addTab(self.manual_box, "Manual")
        self.tabs.addTab(self.auto_box,   "Auto")

        lay.addWidget(self.tabs)

        self.uart_box = create_uart_group_box(self)

        lay.addWidget(self.uart_box)

        return box

    # ═══════════════════════════════════════════════════════
    # UART RX
    # ═══════════════════════════════════════════════════════

    def process_uart_data(self, line):

        try:

            line = str(line).strip()

            if not line:
                return

            # PARSER
            parse_uart_line(line)

            # TEMP CTRL RESPONSE
            pipe_to_response(self, line)

        except Exception as e:

            print("process_uart_data error:", e)

            try:
                self.log_box.append(
                    f"[ERR] process_uart_data: {e}"
                )
            except:
                pass
