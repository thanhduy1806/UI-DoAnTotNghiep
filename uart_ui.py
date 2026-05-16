# from PyQt5.QtWidgets import (
#     QGroupBox,
#     QVBoxLayout,
#     QLabel,
#     QPushButton,
#     QComboBox
# )

# import serial.tools.list_ports

# from uart_handler import UARTHandler


# def create_uart_group_box(parent):

#     group = QGroupBox("UART Connection")

#     layout = QVBoxLayout()

#     parent.port_combo = QComboBox()

#     refresh_ports(parent)

#     parent.refresh_btn = QPushButton("Refresh")
#     parent.connect_btn = QPushButton("Connect")

#     layout.addWidget(QLabel("COM Port"))
#     layout.addWidget(parent.port_combo)

#     layout.addWidget(parent.refresh_btn)
#     layout.addWidget(parent.connect_btn)

#     group.setLayout(layout)

#     parent.refresh_btn.clicked.connect(
#         lambda: refresh_ports(parent)
#     )

#     parent.connect_btn.clicked.connect(
#         lambda: connect_uart(parent)
#     )

#     return group


# def refresh_ports(parent):

#     parent.port_combo.clear()

#     ports = serial.tools.list_ports.comports()

#     for port in ports:
#         parent.port_combo.addItem(port.device)


# def connect_uart(parent):

#     port = parent.port_combo.currentText()

#     if not hasattr(parent, "uart"):

#         parent.uart = UARTHandler(
#             parent.log_box.append,
#             parent.process_uart_data
#         )

#     ok = parent.uart.connect(port)

#     if ok:

#         parent.connect_btn.setText("Disconnect")

#         parent.connect_btn.clicked.disconnect()

#         parent.connect_btn.clicked.connect(
#             lambda: disconnect_uart(parent)
#         )


# def disconnect_uart(parent):

#     parent.uart.disconnect()

#     parent.connect_btn.setText("Connect")

#     parent.connect_btn.clicked.disconnect()

#     parent.connect_btn.clicked.connect(
#         lambda: connect_uart(parent)
#     )

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFrame
)
from PyQt5.QtCore import Qt, QTimer
import serial.tools.list_ports
from uart_handler import UARTHandler
from theme import combo_style, filled_button_style, get_theme, outline_button_style


# ─── Palette ────────────────────────────────────────────────────────────────
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


# ─── Firmware state ─────────────────────────────────────────────────────────
STATE_UNKNOWN    = "unknown"
STATE_BOOTLOADER = "bootloader"
STATE_APP        = "app"


BOOTLOADER_KEYWORDS = ["[xbld]"]
APP_KEYWORDS        = ["debug@mcu:~ $", "system started"]


# ════════════════════════════════════════════════════════════════════════════
# MAIN UI
# ════════════════════════════════════════════════════════════════════════════

def create_uart_group_box(parent):

    parent._fw_state = STATE_UNKNOWN

    group = QGroupBox("UART CONNECTION")
    lay = QVBoxLayout(group)

    # ── COM PORT ────────────────────────────────────────────────────────────
    lay.addWidget(QLabel("COM Port"))

    row = QHBoxLayout()

    parent.port_combo = QComboBox()
    parent.port_combo.setFixedHeight(34)
    parent.port_combo.setStyleSheet(combo_style())
    refresh_ports(parent)

    parent.refresh_btn = QPushButton("Refresh")
    parent.refresh_btn.setFixedWidth(78)
    parent.refresh_btn.clicked.connect(lambda: refresh_ports(parent))

    row.addWidget(parent.port_combo)
    row.addWidget(parent.refresh_btn)
    lay.addLayout(row)

    lay.addWidget(QLabel("Baudrate"))

    parent.baud_combo = QComboBox()
    parent.baud_combo.setEditable(True)
    parent.baud_combo.addItems(BAUDRATES)
    parent.baud_combo.setCurrentText("115200")
    parent.baud_combo.setFixedHeight(34)
    parent.baud_combo.setStyleSheet(combo_style())
    lay.addWidget(parent.baud_combo)

    # ── CONNECT ─────────────────────────────────────────────────────────────
    parent.connect_btn = QPushButton("Connect")
    parent.connect_btn.setFixedHeight(34)
    parent.connect_btn.clicked.connect(lambda: connect_uart(parent))
    lay.addWidget(parent.connect_btn)

    # ── STATE BADGE ─────────────────────────────────────────────────────────
    lay.addWidget(QLabel("Firmware state"))

    parent.state_badge = _StateBadge()
    lay.addWidget(parent.state_badge)

    # ── ACTION ──────────────────────────────────────────────────────────────
    parent.jump_reset_btn = QPushButton("DETECT STATE ?")
    parent.jump_reset_btn.setFixedHeight(34)
    parent.jump_reset_btn.clicked.connect(lambda: jump_or_reset(parent))
    lay.addWidget(parent.jump_reset_btn)

    parent.action_hint = QLabel("state unknown")
    parent.action_hint.setAlignment(Qt.AlignCenter)
    lay.addWidget(parent.action_hint)

    apply_uart_theme(parent)

    return group


# ════════════════════════════════════════════════════════════════════════════
# STATE BADGE (FIXED)
# ════════════════════════════════════════════════════════════════════════════

class _StateBadge(QLabel):

    STYLE = {
        STATE_UNKNOWN:    ("#1A1A2E", "#7A8BA8", "UNKNOWN"),
        STATE_BOOTLOADER: ("#1A1200", "#FFB347", "BOOTLOADER"),
        STATE_APP:        ("#001A0F", "#00E5B0", "APP RUNNING"),
    }

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(34)

        # ✅ FIX: init timer BEFORE set_state
        self._blink_on = True
        self._blink_tmr = QTimer(self)
        self._blink_tmr.timeout.connect(self._blink)

        self._state = STATE_UNKNOWN

        self.set_state(STATE_UNKNOWN)

    def set_state(self, state: str):
        self._state = state

        bg, fg, text = self.STYLE.get(state, self.STYLE[STATE_UNKNOWN])

        self.setText(f"  ●  {text}  ●  ")

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

    if hasattr(parent, "port_combo"):
        parent.port_combo.setStyleSheet(combo_style())
    if hasattr(parent, "baud_combo"):
        parent.baud_combo.setStyleSheet(combo_style())
    if hasattr(parent, "refresh_btn"):
        parent.refresh_btn.setStyleSheet(outline_button_style(t["accent_cyan"]))
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


# ════════════════════════════════════════════════════════════════════════════
# LOGIC
# ════════════════════════════════════════════════════════════════════════════

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
            parent.jump_reset_btn.setText("JUMP → APP")
        elif state == STATE_APP:
            parent.jump_reset_btn.setText("RESET → BOOT")
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


# ════════════════════════════════════════════════════════════════════════════
# UART CONNECT
# ════════════════════════════════════════════════════════════════════════════

def refresh_ports(parent):
    parent.port_combo.clear()
    for p in serial.tools.list_ports.comports():
        parent.port_combo.addItem(p.device)


def connect_uart(parent):
    port = parent.port_combo.currentText()
    if not port:
        return

    try:
        baudrate = int(parent.baud_combo.currentText().strip())
        if baudrate <= 0:
            raise ValueError
    except Exception:
        parent.log_box.append("[UART ERROR] Invalid baudrate")
        return

    if not hasattr(parent, "uart"):
        parent.uart = UARTHandler(
            parent.log_box.append,
            parent.process_uart_data
        )

    if parent.uart.connect(port, baudrate):
        parent.connect_btn.setText("Disconnect")
        parent.connect_btn.clicked.disconnect()
        parent.connect_btn.clicked.connect(lambda: disconnect_uart(parent))
        parent.port_combo.setEnabled(False)
        parent.baud_combo.setEnabled(False)
        set_firmware_state(parent, STATE_UNKNOWN)


def disconnect_uart(parent):
    if hasattr(parent, "uart"):
        parent.uart.disconnect()

    parent.connect_btn.setText("Connect")
    parent.connect_btn.clicked.disconnect()
    parent.connect_btn.clicked.connect(lambda: connect_uart(parent))
    parent.port_combo.setEnabled(True)
    if hasattr(parent, "baud_combo"):
        parent.baud_combo.setEnabled(True)
    set_firmware_state(parent, STATE_UNKNOWN)
