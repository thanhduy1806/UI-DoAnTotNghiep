from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QTabWidget,
    QGridLayout, QFrame, QLabel, QPushButton,
    QSizePolicy, QSplitter, QLineEdit
)
from PyQt5.QtCore import QTimer, Qt

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


BMP390_POLL_INTERVAL_MS = 5 * 60 * 1000


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
        self._bmp390_paused_for_temp_auto = False
        self.bmp390_timer.start(BMP390_POLL_INTERVAL_MS)

        self._apply_theme()
    
        # ═══════════════════════════════════════════════════════
    # SAFE LOG APPEND
    # ═══════════════════════════════════════════════════════

    def _append_log_to_box(self, box, text):

        try:

            if box is None:
                return

            box.append(text)

            # chỉ giữ 200 dòng gần nhất
            doc = box.document()

            MAX_LINES = 200

            while doc.blockCount() > MAX_LINES:

                cursor = box.textCursor()

                cursor.movePosition(cursor.Start)
                cursor.select(cursor.LineUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

        except Exception as e:

            print("log append error:", e)

    # ═══════════════════════════════════════════════════════
    # SAFE PID UPDATE
    # ═══════════════════════════════════════════════════════

    def _append_log(self, text):
        self._append_ttys2_log(text)

    def _append_ttys2_log(self, text):
        self._append_log_to_box(
            getattr(self, "log_box_ttys2", None),
            text,
        )

    def _append_ttys5_log(self, text):
        self._append_log_to_box(
            getattr(self, "log_box_ttys5", None),
            text,
        )

    def _safe_pid_update(self):

        try:
            update_pid_display(self)

        except Exception as e:
            print("PID update error:", e)

    def _poll_bmp390(self):
        try:
            if getattr(self, "_bmp390_paused_for_temp_auto", False):
                return
            if getattr(global_var, "pid_graph_session_active", False):
                return
            if not hasattr(self, "uart") or not self.uart:
                return
            if not getattr(self.uart, "ser", None):
                return

            self.uart.send_command("bmp390_int_read")

        except Exception as e:
            print("BMP390 poll error:", e)

    def pause_bmp390_for_temp_auto(self):
        self._bmp390_paused_for_temp_auto = True
        if hasattr(self, "bmp390_timer") and self.bmp390_timer.isActive():
            self.bmp390_timer.stop()

    def resume_bmp390_after_temp_auto(self, poll_now=True):
        self._bmp390_paused_for_temp_auto = False
        if hasattr(self, "bmp390_timer") and not self.bmp390_timer.isActive():
            self.bmp390_timer.start(BMP390_POLL_INTERVAL_MS)
        if poll_now:
            QTimer.singleShot(300, self._poll_bmp390)

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

        for label in getattr(self, "_log_title_labels", []):
            label.setStyleSheet(
                f"color:{t['accent_cyan']};font-size:13px;font-weight:800;"
                "padding:2px 0;background:transparent;"
            )
        console_input_style = f"""
            QLineEdit {{
                background-color:{t["bg_surface"]};
                border:1.5px solid {t["border"]};
                border-radius:6px;
                color:{t["log_text"]};
                font-family:Consolas;
                font-size:12px;
                font-weight:600;
                padding:1px 8px;
            }}
            QLineEdit:focus {{
                border-color:{t["accent_cyan"]};
            }}
        """
        for command_input in getattr(self, "_console_inputs", {}).values():
            command_input.setStyleSheet(console_input_style)
        console_send_style = f"""
            QPushButton {{
                background-color:{t["bg_surface"]};
                border:1.5px solid {t["accent_cyan"]};
                border-radius:6px;
                color:{t["accent_cyan"]};
                font-size:12px;
                font-weight:800;
                padding:1px 8px;
            }}
            QPushButton:hover {{
                background-color:{t["hover_surface"]};
            }}
            QPushButton:pressed {{
                background-color:{t["button_pressed"]};
            }}
        """
        for send_btn in getattr(self, "_console_send_buttons", {}).values():
            send_btn.setStyleSheet(console_send_style)
            send_btn.setFixedSize(56, 24)

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
        lay.setSpacing(8)
        lay.setContentsMargins(0, 0, 0, 0)

        self._log_title_labels = []
        self._console_inputs = {}
        self._console_send_buttons = {}
        splitter = QSplitter(Qt.Vertical)

        tty2_frame, self.log_box_ttys2 = self._build_log_view(
            "MCU",
            command_target="ttyS2",
        )
        tty5_frame, self.log_box_ttys5 = self._build_log_view(
            "MPU",
            command_target="ttyS5",
        )

        self.log_box = self.log_box_ttys2

        splitter.addWidget(tty2_frame)
        splitter.addWidget(tty5_frame)
        splitter.setSizes([450, 450])

        lay.addWidget(splitter)

        return box

    # ═══════════════════════════════════════════════════════
    # CENTER
    # ═══════════════════════════════════════════════════════

    def _build_log_view(self, title, command_target=None):
        frame = QFrame()
        lay = QVBoxLayout(frame)
        lay.setSpacing(4)
        lay.setContentsMargins(0, 0, 0, 0)

        label = QLabel(title)
        self._log_title_labels.append(label)

        log_box = QTextEdit()
        log_box.setReadOnly(True)

        lay.addWidget(label)
        lay.addWidget(log_box)

        if command_target:
            row = QHBoxLayout()
            row.setSpacing(5)
            row.setContentsMargins(0, 0, 0, 0)

            command_input = QLineEdit()
            display_target = {"ttyS2": "MCU", "ttyS5": "MPU"}.get(
                command_target,
                command_target,
            )
            command_input.setPlaceholderText(f"command {display_target}")
            command_input.setFixedHeight(24)
            command_input.returnPressed.connect(
                lambda target=command_target: self._send_console_command(target)
            )

            send_btn = QPushButton("Send")
            send_btn.setFixedHeight(24)
            send_btn.setFixedWidth(56)
            send_btn.clicked.connect(
                lambda _, target=command_target: self._send_console_command(target)
            )

            self._console_inputs[command_target] = command_input
            self._console_send_buttons[command_target] = send_btn

            if command_target == "ttyS2":
                self.ttys2_input = command_input
                self.ttys2_send_btn = send_btn
            elif command_target == "ttyS5":
                self.ttys5_input = command_input
                self.ttys5_send_btn = send_btn

            row.addWidget(command_input)
            row.addWidget(send_btn)
            lay.addLayout(row)

        return frame, log_box

    def _send_console_command(self, target):
        command_input = getattr(self, "_console_inputs", {}).get(target)
        if command_input is None:
            return

        cmd = command_input.text()
        if not cmd:
            return

        if not hasattr(self, "uart") or not self.uart:
            self._append_console_error(target, "Not connected")
            return

        if target == "ttyS2":
            self.uart.send_command(cmd)
            command_input.clear()
        elif target == "ttyS5" and hasattr(self.uart, "send_ttys5_command"):
            self.uart.send_ttys5_command(cmd)
            command_input.clear()
        else:
            self._append_console_error(target, "Not available")

    def _append_console_error(self, target, message):
        text = f"[{target} TX ERROR] {message}"
        if target == "ttyS5":
            self._append_ttys5_log(text)
        else:
            self._append_ttys2_log(text)

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
        lay.setSpacing(8)

        self.tabs = QTabWidget()

        self.manual_box = create_manual_group_box(self)
        self.auto_box   = create_auto_group_box(self)

        self.tabs.addTab(self.manual_box, "Manual")
        self.tabs.addTab(self.auto_box,   "Auto")
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tabs.setMinimumHeight(self.tabs.sizeHint().height())

        lay.addWidget(self.tabs, stretch=0)

        self.uart_box = create_uart_group_box(self)

        lay.addWidget(self.uart_box, stretch=0)

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
