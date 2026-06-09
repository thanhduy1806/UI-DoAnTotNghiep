from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QTabWidget, QScrollArea,
    QGridLayout, QFrame, QLabel, QPushButton,
    QSizePolicy, QSplitter, QLineEdit
)
from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QTextCursor

import pyqtgraph as pg

# GLOBAL
import global_var

# UART + Parser
from uart_ui import apply_uart_theme, create_uart_group_box, select_if_uart_target
from protocol_parser import parse_uart_line

# Sensors
from bmp390 import apply_on_board_condition_theme, create_on_board_condition_strip
from theme import app_stylesheet, current_theme_name, get_theme
from theme import outline_button_style, toggle_theme

# TEMP SYSTEM
from temp_ctrl import (
    apply_temp_ctrl_theme,
    apply_cli_temp_side_effects,
    create_temp_ctrl_tab,
    update_pid_display,
    pipe_to_response
)

from exp_manual import create_manual_group_box
from exp_manual import apply_manual_theme
from exp_auto import create_auto_group_box


PID_UI_REFRESH_MS = 150


class ConsoleTerminal(QTextEdit):
    def __init__(self, owner, target):
        super().__init__(owner)
        self._owner = owner
        self._target = target
        self._input_start = 0
        self._echo_suppress = []

        self.setReadOnly(False)
        self.setAcceptRichText(False)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.setProperty("command_target", target)
        self.installEventFilter(owner)

    def append_output(self, text):
        text = self._format_terminal_text(str(text))
        if self._should_suppress_echo(text):
            return

        pending_input, cursor_offset = self._detach_pending_input()

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        QTextEdit.append(self, text)
        self.mark_input_start()
        self._restore_pending_input(pending_input, cursor_offset)

    def mark_input_start(self):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self._input_start = cursor.position()

    def trim_history(self, max_lines):
        pending_input, cursor_offset = self._detach_pending_input()
        doc = self.document()

        while doc.blockCount() > max_lines:
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.select(QTextCursor.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        self.mark_input_start()
        self._restore_pending_input(pending_input, cursor_offset)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._submit_current_input()
            return

        if event.key() == Qt.Key_Home:
            cursor = self.textCursor()
            cursor.setPosition(self._input_start)
            self.setTextCursor(cursor)
            return

        if event.key() in (Qt.Key_Backspace, Qt.Key_Left):
            cursor = self.textCursor()
            if cursor.position() <= self._input_start and not cursor.hasSelection():
                return

        self._keep_cursor_in_input()
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def _submit_current_input(self):
        cmd = self._current_input()
        if not self._owner._send_console_text_command(self._target, cmd):
            return

        if cmd:
            self._echo_suppress.append(cmd.strip())
            self._echo_suppress = self._echo_suppress[-5:]

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self.mark_input_start()

    def _current_input(self):
        return self.toPlainText()[self._input_start:]

    def _detach_pending_input(self):
        full_text = self.toPlainText()
        start = max(0, min(self._input_start, len(full_text)))
        pending_input = full_text[start:]

        cursor = self.textCursor()
        cursor_offset = max(0, min(cursor.position() - start, len(pending_input)))

        if pending_input:
            remove_cursor = self.textCursor()
            remove_cursor.setPosition(start)
            remove_cursor.setPosition(len(full_text), QTextCursor.KeepAnchor)
            remove_cursor.removeSelectedText()
            self.setTextCursor(remove_cursor)
            self._input_start = start

        return pending_input, cursor_offset

    def _restore_pending_input(self, pending_input, cursor_offset):
        if not pending_input:
            return

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self.insertPlainText(pending_input)

        restored_pos = self._input_start + max(
            0,
            min(int(cursor_offset), len(pending_input)),
        )
        cursor = self.textCursor()
        cursor.setPosition(restored_pos)
        self.setTextCursor(cursor)

    def _keep_cursor_in_input(self):
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectionStart() < self._input_start:
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)
            return
        if cursor.position() < self._input_start:
            cursor.movePosition(QTextCursor.End)
            self.setTextCursor(cursor)

    def _format_terminal_text(self, text):
        stripped = text.strip()
        if stripped == ">>>":
            return ">>> "
        if stripped.startswith("root@") and stripped.endswith(("#", "$")):
            return stripped + " "
        return text

    def _should_suppress_echo(self, text):
        stripped = text.strip()
        if not stripped:
            return False

        for cmd in list(self._echo_suppress):
            if stripped == cmd or stripped in (f">>> {cmd}", f">>>{cmd}"):
                self._echo_suppress.remove(cmd)
                return True

            if stripped.endswith(cmd):
                prefix = stripped[:-len(cmd)].strip()
                if prefix.endswith(("#", "$", ">>>")):
                    self._echo_suppress.remove(cmd)
                    return True

        return False


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

        self.timer.start(PID_UI_REFRESH_MS)

        self.bmp390_timer = QTimer()
        self.bmp390_timer.timeout.connect(self._poll_bmp390)
        # Disabled for now so bmp390_int_read cannot interrupt interactive UART flows.
        # self.bmp390_timer.start(10000)

        self._apply_theme()
    
        # ═══════════════════════════════════════════════════════
    # SAFE LOG APPEND
    # ═══════════════════════════════════════════════════════

    def _append_log_to_box(self, box, text):

        try:

            if box is None:
                return

            if hasattr(box, "append_output"):
                box.append_output(text)
            else:
                box.append(text)

            # chỉ giữ 200 dòng gần nhất
            MAX_LINES = 200
            if hasattr(box, "trim_history"):
                box.trim_history(MAX_LINES)
                return

            doc = box.document()

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
        if str(text).startswith("[WIZARD]"):
            return
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
            if not getattr(global_var, "pid_display_dirty", False):
                return
            update_pid_display(self)
            global_var.pid_display_dirty = False

        except Exception as e:
            print("PID update error:", e)

    def _poll_bmp390(self):
        try:
            if not hasattr(self, "uart") or not self.uart:
                return
            if not getattr(self.uart, "ser", None):
                return
            if self._is_wizard_active():
                return
            if getattr(self, "_connection_mode", None) == "uart":
                if getattr(self.uart, "active_target", None) != "ttyS2":
                    return
                if not getattr(self.uart, "_minicom_ready", False):
                    return

            self.uart.send_command("bmp390_int_read")

        except Exception as e:
            print("BMP390 poll error:", e)

    def _is_wizard_active(self):
        wizard = getattr(self, "_wizard_sm", None)
        return bool(wizard and wizard.is_active())

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
        self._console_terminals = {}
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

        if command_target:
            log_box = ConsoleTerminal(self, command_target)
        else:
            log_box = QTextEdit()
            log_box.setReadOnly(True)

        lay.addWidget(label)
        lay.addWidget(log_box)

        if command_target:
            self._console_terminals[command_target] = log_box

        return frame, log_box

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusIn:
            target = obj.property("command_target")
            if target in ("ttyS2", "ttyS5"):
                self._activate_command_target(target, notify=False)
        elif event.type() == QEvent.KeyPress:
            target = obj.property("command_target")
            if (
                target in ("ttyS2", "ttyS5")
                and event.key() == Qt.Key_C
                and event.modifiers() & Qt.ControlModifier
            ):
                if hasattr(obj, "textCursor") and obj.textCursor().hasSelection():
                    obj.copy()
                    event.accept()
                    return True
                self._send_console_interrupt(target)
                event.accept()
                return True

        return super().eventFilter(obj, event)

    def _send_console_interrupt(self, target):
        if not hasattr(self, "uart") or not self.uart:
            self._append_console_error(target, "Not connected")
            return

        if not self._activate_command_target(target, notify=True):
            return

        command_input = getattr(self, "_console_inputs", {}).get(target)
        if command_input is not None:
            command_input.clear()

        if target == "ttyS2" and hasattr(self.uart, "send_interrupt"):
            self.uart.send_interrupt()
        elif target == "ttyS5" and hasattr(self.uart, "send_ttys5_interrupt"):
            self.uart.send_ttys5_interrupt()
        else:
            self._append_console_error(target, "Interrupt not available")

    def _send_console_command(self, target):
        command_input = getattr(self, "_console_inputs", {}).get(target)
        if command_input is None:
            return

        cmd = command_input.text()
        if self._send_console_text_command(target, cmd):
            command_input.clear()

    def _send_console_text_command(self, target, cmd):
        normalized_cmd = str(cmd).strip().lower()

        if not hasattr(self, "uart") or not self.uart:
            self._append_console_error(target, "Not connected")
            return False

        if not self._activate_command_target(target, notify=True):
            return False

        is_interrupt = normalized_cmd in {"ctrl+c", "^c", "interrupt"}

        if target == "ttyS2":
            apply_cli_temp_side_effects(self, cmd)
            if is_interrupt and hasattr(self.uart, "send_interrupt"):
                self.uart.send_interrupt()
            else:
                self.uart.send_command(cmd)
            return True

        if target == "ttyS5" and hasattr(self.uart, "send_ttys5_command"):
            if is_interrupt and hasattr(self.uart, "send_ttys5_interrupt"):
                self.uart.send_ttys5_interrupt()
            else:
                self.uart.send_ttys5_command(cmd)
            return True

        self._append_console_error(target, "Not available")
        return False

    def _activate_command_target(self, target, notify=True):
        if getattr(self, "_connection_mode", None) != "uart":
            return True

        if target not in ("ttyS2", "ttyS5"):
            return True

        connected = bool(getattr(self, "_connection_active", False))
        uart = getattr(self, "uart", None)
        previous_target = getattr(uart, "active_target", None)
        pending_target = getattr(uart, "_pending_target", None)

        select_if_uart_target(self, target)

        if not connected or not uart or not hasattr(uart, "switch_target"):
            return True

        if previous_target != target:
            if notify:
                if pending_target == target:
                    self._append_console_info(target, "IF UART target is switching")
                else:
                    self._append_console_info(target, "Switching IF UART target, wait for READY")
            return False

        if not getattr(uart, "_bridge_ready", False):
            if notify:
                self._append_console_info(target, "IF UART target is not ready")
            return False

        return True

    def _append_console_info(self, target, message):
        text = f"[{target}] {message}"
        if target == "ttyS5":
            self._append_ttys5_log(text)
        else:
            self._append_ttys2_log(text)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        box = QFrame()
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        lay = QVBoxLayout(box)
        lay.setSpacing(8)
        lay.setContentsMargins(0, 0, 0, 0)

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

        scroll.setWidget(box)
        self.right_scroll_area = scroll

        return scroll

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

        except Exception as e:

            print("process_uart_data error:", e)

            try:
                self.log_box.append(
                    f"[ERR] process_uart_data: {e}"
                )
            except:
                pass
