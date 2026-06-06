from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFrame, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer

from uart_handler import SSHMinicomHandler
from theme import combo_style, filled_button_style, get_theme, outline_button_style


BAUDRATES = [
    "9600",
    "19200",
    "38400",
    "57600",
    "115200",
    "230400",
    "460800",
    "921600",
]

DEFAULT_SSH_HOST = "10.241.97.88"
DEFAULT_SSH_USER = "root"
DEFAULT_SSH_PORT = "22"

STATE_UNKNOWN = "unknown"
STATE_BOOTLOADER = "bootloader"
STATE_APP = "app"

BOOTLOADER_KEYWORDS = ["[xbld]"]
APP_KEYWORDS = ["debug@mcu:~ $", "system started"]


def create_uart_group_box(parent):
    parent._fw_state = STATE_UNKNOWN

    group = QGroupBox("SSH CONNECTION")
    lay = QVBoxLayout(group)
    lay.setSpacing(8)

    lay.addWidget(QLabel("Host IP"))
    parent.ssh_host_edit = QLineEdit(DEFAULT_SSH_HOST)
    parent.ssh_host_edit.setPlaceholderText("10.241.97.88")
    parent.ssh_host_edit.setFixedHeight(34)
    lay.addWidget(parent.ssh_host_edit)

    user_row = QHBoxLayout()
    user_col = QVBoxLayout()
    pass_col = QVBoxLayout()

    user_col.addWidget(QLabel("User"))
    parent.ssh_user_edit = QLineEdit(DEFAULT_SSH_USER)
    parent.ssh_user_edit.setFixedHeight(34)
    user_col.addWidget(parent.ssh_user_edit)

    pass_col.addWidget(QLabel("Password"))
    parent.ssh_password_edit = QLineEdit()
    parent.ssh_password_edit.setEchoMode(QLineEdit.Password)
    parent.ssh_password_edit.setFixedHeight(34)
    pass_col.addWidget(parent.ssh_password_edit)

    user_row.addLayout(user_col)
    user_row.addLayout(pass_col)
    lay.addLayout(user_row)

    conn_row = QHBoxLayout()
    port_col = QVBoxLayout()
    baud_col = QVBoxLayout()

    port_col.addWidget(QLabel("SSH Port"))
    parent.ssh_port_edit = QLineEdit(DEFAULT_SSH_PORT)
    parent.ssh_port_edit.setFixedHeight(34)
    parent.ssh_port_edit.setFixedWidth(76)
    port_col.addWidget(parent.ssh_port_edit)

    baud_col.addWidget(QLabel("Serial baudrate"))
    parent.baud_combo = QComboBox()
    parent.baud_combo.setEditable(True)
    parent.baud_combo.addItems(BAUDRATES)
    parent.baud_combo.setCurrentText("115200")
    parent.baud_combo.setFixedHeight(34)
    baud_col.addWidget(parent.baud_combo)

    conn_row.addLayout(port_col)
    conn_row.addLayout(baud_col)
    lay.addLayout(conn_row)

    parent.connect_btn = QPushButton("Connect SSH")
    parent.connect_btn.setFixedHeight(34)
    parent.connect_btn.clicked.connect(lambda: connect_uart(parent))
    lay.addWidget(parent.connect_btn)

    lay.addWidget(QLabel("Firmware state"))
    parent.state_badge = _StateBadge()
    lay.addWidget(parent.state_badge)

    parent.jump_reset_btn = QPushButton("DETECT STATE ?")
    parent.jump_reset_btn.setFixedHeight(34)
    parent.jump_reset_btn.clicked.connect(lambda: jump_or_reset(parent))
    lay.addWidget(parent.jump_reset_btn)

    parent.action_hint = QLabel("state unknown")
    parent.action_hint.setAlignment(Qt.AlignCenter)
    lay.addWidget(parent.action_hint)

    apply_uart_theme(parent)

    return group


class _StateBadge(QLabel):
    STYLE = {
        STATE_UNKNOWN: ("#1A1A2E", "#7A8BA8", "UNKNOWN"),
        STATE_BOOTLOADER: ("#1A1200", "#FFB347", "BOOTLOADER"),
        STATE_APP: ("#001A0F", "#00E5B0", "APP RUNNING"),
    }

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(34)
        self._blink_on = True
        self._blink_tmr = QTimer(self)
        self._blink_tmr.timeout.connect(self._blink)
        self._state = STATE_UNKNOWN
        self.set_state(STATE_UNKNOWN)

    def set_state(self, state: str):
        self._state = state

        bg, fg, text = self.STYLE.get(state, self.STYLE[STATE_UNKNOWN])
        self.setText(f"  *  {text}  *  ")

        self._base_bg = bg
        self._fg = fg
        self.setStyleSheet(self._style(bg, fg, border=fg))

        if state == STATE_BOOTLOADER:
            self._blink_tmr.start(500)
        else:
            self._blink_tmr.stop()
            self._blink_on = True

    def _blink(self):
        self._blink_on = not self._blink_on
        border = self._fg if self._blink_on else "#3E2800"
        self.setStyleSheet(self._style(self._base_bg, self._fg, border))

    def _style(self, bg, fg, border):
        return f"""
        QLabel {{
            background-color: {bg};
            border: 1.5px solid {border};
            border-radius: 6px;
            color: {fg};
            font-family: Consolas;
            font-weight: 700;
            font-size: 13px;
        }}
        """


def apply_uart_theme(parent):
    t = get_theme()

    for attr in (
        "ssh_host_edit",
        "ssh_user_edit",
        "ssh_password_edit",
        "ssh_port_edit",
    ):
        widget = getattr(parent, attr, None)
        if widget is not None:
            widget.setStyleSheet(_line_edit_style())

    if hasattr(parent, "baud_combo"):
        parent.baud_combo.setStyleSheet(combo_style())
    if hasattr(parent, "connect_btn"):
        parent.connect_btn.setStyleSheet(filled_button_style(t["accent_teal"]))
    if hasattr(parent, "jump_reset_btn"):
        parent.jump_reset_btn.setStyleSheet(outline_button_style(t["accent_cyan"]))
    if hasattr(parent, "action_hint"):
        parent.action_hint.setStyleSheet(
            f"color:{t['text_secondary']};font-size:13px;font-weight:600;"
        )
    if hasattr(parent, "state_badge"):
        parent.state_badge.set_state(parent._fw_state)


def _line_edit_style():
    t = get_theme()
    return f"""
        QLineEdit {{
            background-color: {t["bg_surface"]};
            border: 1.5px solid {t["border"]};
            border-radius: 6px;
            color: {t["text_primary"]};
            font-size: 13px;
            font-weight: 600;
            padding: 4px 10px;
        }}
        QLineEdit:focus {{
            border-color: {t["accent_cyan"]};
        }}
        QLineEdit:disabled {{
            color: {t["text_secondary"]};
            border-color: {t["border"]};
        }}
    """


def jump_or_reset(parent):
    if not hasattr(parent, "uart") or not parent.uart:
        return

    state = parent._fw_state

    if state == STATE_BOOTLOADER:
        parent.uart.send_command("j")
        parent.uart.send_command("j")
    elif state == STATE_APP:
        parent.uart.send_command("reset")
    else:
        parent.uart.send_command("?")


def set_firmware_state(parent, state: str):
    parent._fw_state = state

    if hasattr(parent, "state_badge"):
        parent.state_badge.set_state(state)

    if hasattr(parent, "jump_reset_btn"):
        if state == STATE_BOOTLOADER:
            parent.jump_reset_btn.setText("JUMP -> APP")
        elif state == STATE_APP:
            parent.jump_reset_btn.setText("RESET -> BOOT")
        else:
            parent.jump_reset_btn.setText("DETECT STATE ?")

    if hasattr(parent, "action_hint"):
        parent.action_hint.setText(
            "send jj" if state == STATE_BOOTLOADER else
            "send reset" if state == STATE_APP else
            "detect first"
        )


def auto_detect_state(parent, line: str):
    l = line.lower()

    if any(k in l for k in BOOTLOADER_KEYWORDS):
        set_firmware_state(parent, STATE_BOOTLOADER)
    elif any(k in l for k in APP_KEYWORDS):
        set_firmware_state(parent, STATE_APP)


def connect_uart(parent):
    host = parent.ssh_host_edit.text().strip()
    username = parent.ssh_user_edit.text().strip() or DEFAULT_SSH_USER
    password = parent.ssh_password_edit.text()

    if not host:
        _log_ttys2(parent, "[SSH ERROR] Host IP is empty")
        return

    try:
        ssh_port = int(parent.ssh_port_edit.text().strip() or DEFAULT_SSH_PORT)
        if ssh_port <= 0:
            raise ValueError
    except Exception:
        _log_ttys2(parent, "[SSH ERROR] Invalid SSH port")
        return

    try:
        baudrate = int(parent.baud_combo.currentText().strip())
        if baudrate <= 0:
            raise ValueError
    except Exception:
        _log_ttys2(parent, "[SSH ERROR] Invalid serial baudrate")
        return

    log_ttys2 = getattr(parent, "_append_ttys2_log", None)
    log_ttys5 = getattr(parent, "_append_ttys5_log", None)
    if log_ttys2 is None:
        log_ttys2 = parent.log_box.append
    if log_ttys5 is None:
        log_ttys5 = log_ttys2

    if not hasattr(parent, "uart") or not isinstance(parent.uart, SSHMinicomHandler):
        parent.uart = SSHMinicomHandler(
            log_ttys2,
            parent.process_uart_data,
            log_ttys5,
        )

    if parent.uart.connect(host, username, password, ssh_port, baudrate):
        parent.connect_btn.setText("Disconnect")
        parent.connect_btn.clicked.disconnect()
        parent.connect_btn.clicked.connect(lambda: disconnect_uart(parent))
        _set_connect_fields_enabled(parent, False)
        set_firmware_state(parent, STATE_UNKNOWN)


def disconnect_uart(parent):
    if hasattr(parent, "uart") and parent.uart:
        parent.uart.disconnect()

    parent.connect_btn.setText("Connect SSH")
    parent.connect_btn.clicked.disconnect()
    parent.connect_btn.clicked.connect(lambda: connect_uart(parent))
    _set_connect_fields_enabled(parent, True)
    set_firmware_state(parent, STATE_UNKNOWN)


def _set_connect_fields_enabled(parent, enabled):
    for attr in (
        "ssh_host_edit",
        "ssh_user_edit",
        "ssh_password_edit",
        "ssh_port_edit",
        "baud_combo",
    ):
        widget = getattr(parent, attr, None)
        if widget is not None:
            widget.setEnabled(enabled)


def _log_ttys2(parent, text):
    callback = getattr(parent, "_append_ttys2_log", None)
    if callback is not None:
        callback(text)
    elif hasattr(parent, "log_box"):
        parent.log_box.append(text)
