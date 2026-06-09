try:
    import serial
except ImportError:
    serial = None

import threading
import time
import re
import socket

try:
    import paramiko
except ImportError:
    paramiko = None

from PyQt5.QtCore import QObject, pyqtSignal, Qt


class UARTHandler(QObject):                    # ← kế thừa QObject

    # Signal emit từ thread phụ → Qt tự queue về main thread
    sig_log  = pyqtSignal(str)
    sig_data = pyqtSignal(str)

    _MAX_HEX_LOG_BYTES = 64

    def __init__(self, log_callback, data_callback):
        super().__init__()                     # ← bắt buộc khi dùng QObject

        self.ser     = None
        self.running = False

        # Connect signal → callback, Qt.QueuedConnection đảm bảo
        # callback luôn chạy trên main thread dù signal emit từ thread phụ
        self.sig_log.connect(log_callback,   Qt.QueuedConnection)
        self.sig_data.connect(data_callback, Qt.QueuedConnection)

    # ─────────────────────────────────────────────
    # CONNECT
    # ─────────────────────────────────────────────
    def connect(self, port, baudrate=115200):
        if serial is None:
            self.sig_log.emit("[UART ERROR] pyserial is not installed")
            return False

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=0.1
            )
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self.running = True

            threading.Thread(
                target=self.read_thread,
                daemon=True
            ).start()

            self.sig_log.emit(f"[UART] Connected {port} @ {baudrate}")
            return True

        except Exception as e:
            self.sig_log.emit(f"[UART ERROR] {e}")
            return False

    # ─────────────────────────────────────────────
    # DISCONNECT
    # ─────────────────────────────────────────────
    def disconnect(self):
        self.running = False
        try:
            if self.ser:
                self.ser.close()
                self.ser = None
        except Exception:
            pass
        self.sig_log.emit("[UART] Disconnected")

    # ─────────────────────────────────────────────
    # SEND COMMAND
    # ─────────────────────────────────────────────
    def send_command(self, cmd):
        if not self.ser:
            return
        try:
            self.ser.write((cmd + "\n").encode())
            self.sig_log.emit(f"[TX] {cmd}")
        except Exception as e:
            self.sig_log.emit(f"[UART TX ERROR] {e}")

    def _decode_rx_line(self, raw_line: bytes):
        line = raw_line.strip(b"\r\n")
        if not line:
            return None, None

        printable = sum(1 for b in line if b in (9, 13) or 32 <= b <= 126)
        ratio = printable / len(line)

        # Text protocol lines should be mostly printable ASCII. If the MCU sends
        # binary/status bytes, show HEX in the log and keep them out of parsers.
        if ratio < 0.85:
            sample = line[:self._MAX_HEX_LOG_BYTES]
            hex_text = " ".join(f"{b:02X}" for b in sample)
            if len(line) > self._MAX_HEX_LOG_BYTES:
                hex_text += " ..."
            return None, f"[RX HEX] {hex_text}"

        text = line.decode("ascii", errors="replace")
        clean = "".join(ch for ch in text if ch == "\t" or 32 <= ord(ch) <= 126)
        clean = clean.strip()
        return clean or None, None

    # ─────────────────────────────────────────────
    # RX THREAD
    # ─────────────────────────────────────────────
    def read_thread(self):
        buffer = b""
        while self.running:
            try:
                if self.ser and self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)

                    if not data:
                        continue

                    buffer += data

                    while b"\n" in buffer:
                        raw_line, buffer = buffer.split(b"\n", 1)
                        line, hex_log = self._decode_rx_line(raw_line)
                        if hex_log:
                            self.sig_log.emit(hex_log)
                        if line:
                            self.sig_log.emit(f"[RX] {line}")   # ← emit, không gọi trực tiếp
                            self.sig_data.emit(line)             # ← emit, không gọi trực tiếp

            except Exception as e:
                self.sig_log.emit(f"[UART RX ERROR] {e}")

            time.sleep(0.03)


class SSHMinicomHandler(QObject):
    """SSH transport that exposes ttyS2 as the legacy command/data UART."""

    sig_log_ttys2 = pyqtSignal(str)
    sig_log_ttys5 = pyqtSignal(str)
    sig_data = pyqtSignal(str)

    _ANSI_RE = re.compile(
        r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
    )
    _MINICOM_NOISE = (
        "welcome to minicom",
        "options:",
        "compiled on",
        "minicom -d /dev/tty",
        "port /dev/tty",
        "press ctrl-a z",
        "ctrl-a z for help",
    )
    _COMMAND_CHAR_DELAYS = {
        "ttyS2": 0.001,
        "ttyS5": 0.001,
    }
    _TTYS2_PARTIAL_PROMPTS = (
        "please enter y or n",
        "please entter y or n",
        "profile index:",
        "main ntc:",
        "sec ntc:",
        "tec mask:",
        "heater mask:",
        "setpoint (0.01*c):",
        "main-sec delta (0.01*c):",
        "step count:",
        "step[",
        "save? (y/n):",
        "saved",
    )

    def __init__(self, log_ttys2_callback, data_callback, log_ttys5_callback=None):
        super().__init__()

        self.clients = {}
        self.channels = {}
        self.buffers = {}
        self.channel_states = {}
        self.channel_devices = {}
        self.channel_retry_counts = {}
        self.channel_prompt_ready = {}
        self.channel_pending_commands = {}
        self.channel_runtime_modes = {}
        self.channel_partial_prompts = {}
        self.channel_window_histories = {}
        self.channel_rx_line_chars = {}
        self.channel_rx_cursors = {}
        self.running = False
        self.ser = None
        self._send_lock = threading.Lock()

        self.sig_log_ttys2.connect(log_ttys2_callback, Qt.QueuedConnection)
        self.sig_log_ttys5.connect(
            log_ttys5_callback or log_ttys2_callback,
            Qt.QueuedConnection,
        )
        self.sig_data.connect(data_callback, Qt.QueuedConnection)

    def connect(
        self,
        host,
        username="root",
        password="",
        ssh_port=22,
        baudrate=115200,
    ):
        if paramiko is None:
            self.sig_log_ttys2.emit(
                "[SSH ERROR] paramiko is not installed. "
                "Run: .\\.venv\\Scripts\\python.exe -m pip install paramiko"
            )
            return False

        try:
            self.disconnect(quiet=True)

            self.running = True
            self.ser = True
            self._open_minicom_channel(
                "ttyS2",
                "/dev/ttyS2",
                baudrate,
                host,
                username,
                password,
                ssh_port,
            )
            self._open_minicom_channel(
                "ttyS5",
                "/dev/ttyS5",
                baudrate,
                host,
                username,
                password,
                ssh_port,
            )
            return True

        except Exception as e:
            self.sig_log_ttys2.emit(f"[SSH ERROR] {e}")
            self.sig_log_ttys5.emit(f"[SSH ERROR] {e}")
            self.disconnect(quiet=True)
            return False

    def _open_minicom_channel(self, name, device, baudrate, host, username, password, ssh_port):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=host,
            port=int(ssh_port),
            username=username,
            password=password or None,
            look_for_keys=False,
            allow_agent=False,
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
        )

        channel = client.invoke_shell(term="vt100", width=160, height=48)
        channel.settimeout(0.0)

        self.clients[name] = client
        self.channels[name] = channel
        self.buffers[name] = ""
        self.channel_states[name] = "shell_wait"
        self.channel_devices[name] = (device, int(baudrate))
        self.channel_retry_counts[name] = 0
        self.channel_prompt_ready[name] = False
        self.channel_pending_commands[name] = []
        self.channel_runtime_modes[name] = "shell"
        self.channel_partial_prompts[name] = None
        self.channel_window_histories[name] = ""
        self.channel_rx_line_chars[name] = []
        self.channel_rx_cursors[name] = 0

        self._emit_log(name, f"[SSH] Connected {username}@{host}:{ssh_port}")

        with self._send_lock:
            channel.send("\n")

        threading.Thread(
            target=self._read_thread,
            args=(name, channel),
            daemon=True,
        ).start()

    def disconnect(self, quiet=False):
        self.running = False

        for channel in list(self.channels.values()):
            try:
                channel.close()
            except Exception:
                pass

        self.channels.clear()
        self.buffers.clear()
        self.channel_states.clear()
        self.channel_devices.clear()
        self.channel_retry_counts.clear()
        self.channel_prompt_ready.clear()
        self.channel_pending_commands.clear()
        self.channel_runtime_modes.clear()
        self.channel_partial_prompts.clear()
        self.channel_window_histories.clear()
        self.channel_rx_line_chars.clear()
        self.channel_rx_cursors.clear()

        for client in list(self.clients.values()):
            try:
                client.close()
            except Exception:
                pass

        self.clients.clear()
        self.ser = None

        if not quiet:
            self.sig_log_ttys2.emit("[SSH] Disconnected")
            self.sig_log_ttys5.emit("[SSH] Disconnected")

    def send_command(self, cmd):
        self._send_to_channel("ttyS2", cmd)

    def send_ttys5_command(self, cmd):
        self._send_to_channel("ttyS5", cmd)

    def send_interrupt(self):
        self._send_raw_to_channel("ttyS2", "\x03", char_delay=0.0)

    def send_ttys5_interrupt(self):
        self.channel_pending_commands["ttyS5"] = []
        self._send_raw_to_channel("ttyS5", "\x03", char_delay=0.0)

    def _send_to_channel(self, name, cmd):
        channel = self.channels.get(name)
        if not self.running or not channel:
            self._emit_log(name, f"[{name} TX ERROR] Not connected")
            return

        try:
            if name == "ttyS5":
                mode = self.channel_runtime_modes.get(name, "shell")
                if mode == "repl":
                    self._queue_or_send_repl_command(name, str(cmd))
                else:
                    self.channel_partial_prompts[name] = None
                    self._send_raw_to_channel(
                        name,
                        str(cmd) + "\r",
                        char_delay=self._COMMAND_CHAR_DELAYS.get(name, 0.0),
                    )
            else:
                self._send_raw_to_channel(
                    name,
                    str(cmd).rstrip("\r\n") + "\r",
                    char_delay=self._COMMAND_CHAR_DELAYS.get(name, 0.001),
                )
        except Exception as e:
            self._emit_log(name, f"[{name} TX ERROR] {e}")

    def _send_raw_to_channel(self, name, text, char_delay=None):
        channel = self.channels.get(name)
        if not self.running or not channel:
            self._emit_log(name, f"[{name} TX ERROR] Not connected")
            return
        self._write_channel_command_text(name, text, char_delay=char_delay)

    def _read_thread(self, name, channel):
        while self.running and not channel.closed:
            try:
                if channel.recv_ready():
                    data = channel.recv(4096)
                    if not data:
                        break
                    self._process_rx(name, data)

            except socket.timeout:
                pass
            except Exception as e:
                if self.running:
                    self._emit_log(name, f"[{name} RX ERROR] {e}")
                break

            time.sleep(0.03)

    def _process_rx(self, name, data):
        text = data.decode("utf-8", errors="replace")
        text = self._ANSI_RE.sub("", text)
        text = text.replace("\x00", "")

        if name != "ttyS2":
            text = text.replace("\r\n", "\n").replace("\r", "\n")

            self.buffers[name] = self.buffers.get(name, "") + text
            self._handle_session_prompts(name)

            while "\n" in self.buffers[name]:
                raw_line, self.buffers[name] = self.buffers[name].split("\n", 1)
                self._handle_line(name, raw_line)

            self._handle_runtime_partial_prompt(name)
            return

        # Milestone "lam MCU terminal nhu that":
        # old ttyS2 path flattened every CR into LF:
        # text = text.replace("\r\n", "\n").replace("\r", "\n")
        # self.buffers[name] = self.buffers.get(name, "") + text
        # That made minicom redraw/prompt traffic look like log lines instead of
        # a terminal stream, so MCU prompts/echoes were getting mangled.
        lines = []
        idx = 0
        text_len = len(text)

        line_chars = self.channel_rx_line_chars.get(name, [])
        cursor = int(self.channel_rx_cursors.get(name, 0))
        history = self.channel_window_histories.get(name, "")

        while idx < text_len:
            ch = text[idx]

            if ch == "\r":
                if idx + 1 < text_len and text[idx + 1] == "\n":
                    line_text = "".join(line_chars)
                    lines.append(line_text)
                    history = (history + line_text + "\n")[-5000:]
                    line_chars = []
                    cursor = 0
                    idx += 2
                    continue

                # Bare CR in minicom often means redraw current line.
                line_chars = []
                cursor = 0
                idx += 1
                continue

            if ch == "\n":
                line_text = "".join(line_chars)
                lines.append(line_text)
                history = (history + line_text + "\n")[-5000:]
                line_chars = []
                cursor = 0
                idx += 1
                continue

            if ch in ("\b", "\x7f"):
                if cursor > 0:
                    cursor -= 1
                    if cursor < len(line_chars):
                        line_chars.pop(cursor)
                idx += 1
                continue

            if ch == "\t" or 32 <= ord(ch) <= 126:
                if cursor < len(line_chars):
                    line_chars[cursor] = ch
                else:
                    line_chars.append(ch)
                cursor += 1

            idx += 1

        self.channel_rx_line_chars[name] = line_chars
        self.channel_rx_cursors[name] = cursor
        self.channel_window_histories[name] = history
        self.buffers[name] = (history + "".join(line_chars))[-5000:]

        self._handle_session_prompts(name)

        for raw_line in lines:
            self._handle_line(name, raw_line)

        self._handle_runtime_partial_prompt(name)

    def _handle_session_prompts(self, name):
        state = self.channel_states.get(name, "")
        window = self.buffers.get(name, "")[-800:]

        if state == "shell_wait" and self._looks_like_shell_prompt(window):
            prompt = self._extract_shell_prompt_text(window)
            if prompt:
                self._emit_log(name, prompt)
            self._clear_channel_window(name)
            self._start_minicom_on_channel(name)
            return

        if state == "lock_cleanup_wait" and self._looks_like_shell_prompt(window):
            prompt = self._extract_shell_prompt_text(window)
            if prompt:
                self._emit_log(name, prompt)
            self._clear_channel_window(name)
            self._start_minicom_on_channel(name)
            return

    def _handle_line(self, name, raw_line):
        cleaned = self._apply_backspaces(str(raw_line))
        line = "".join(
            ch for ch in cleaned.strip()
            if ch == "\t" or 32 <= ord(ch) <= 126
        ).strip()

        if not line:
            return

        lower = line.lower()
        if any(part in lower for part in self._MINICOM_NOISE):
            return
        if "device /dev/tty" in lower and "is locked" in lower:
            self._emit_log(name, line)
            self._handle_locked_device(name, line)
            return

        self._emit_log(name, line)
        self._handle_runtime_prompt(name, line)

        if name == "ttyS2":
            self.sig_data.emit(line)
            if "unknown command:" in lower or lower == "cancelled" or lower.endswith("cancelled"):
                self._emit_synthetic_mcu_prompt(name)

    def _emit_log(self, name, text):
        if name == "ttyS5":
            self.sig_log_ttys5.emit(text)
        else:
            self.sig_log_ttys2.emit(text)

    def _start_minicom_on_channel(self, name):
        self.channel_states[name] = "minicom_starting"
        device, baudrate = self.channel_devices.get(name, ("/dev/ttyS2", 115200))
        self._write_channel_command_text(
            name,
            f"minicom -D {device} -b {int(baudrate)}\n",
        )

    def _handle_locked_device(self, name, line):
        retries = self.channel_retry_counts.get(name, 0)
        device, _ = self.channel_devices.get(name, ("/dev/ttyS2", 115200))
        tty_name = device.rsplit("/", 1)[-1]

        if retries >= 1:
            self._emit_log(name, f"[SSH] {device} is still locked after retry")
            self.channel_states[name] = "shell_wait"
            return

        self.channel_retry_counts[name] = retries + 1
        self.channel_states[name] = "lock_cleanup_wait"
        self._emit_log(name, f"[SSH] Retrying {device} after clearing stale lock/process")
        cleanup_cmd = (
            f"pkill -f 'minicom -D {device}' >/dev/null 2>&1; "
            f"rm -f /var/lock/LCK..{tty_name} /var/lock/lockdev/LCK..{tty_name}\n"
        )
        self._write_channel_command_text(name, cleanup_cmd)

    def _write_channel_command_text(self, name, text, char_delay=None):
        channel = self.channels.get(name)
        if not channel:
            return
        with self._send_lock:
            payload = str(text).encode("utf-8", errors="replace")
            delay = 0.0 if char_delay is None else float(char_delay)
            if delay <= 0:
                if hasattr(channel, "sendall"):
                    channel.sendall(payload)
                else:
                    channel.send(payload)
                return

            for byte in payload:
                chunk = bytes([byte])
                if hasattr(channel, "sendall"):
                    channel.sendall(chunk)
                else:
                    channel.send(chunk)
                time.sleep(delay)

    def _looks_like_shell_prompt(self, window):
        tail = window[-500:]
        return bool(re.search(r"(^|\n)[^\n]*(root@pay-(?:if|exp)|pay-(?:if|exp))[^\n]*#\s*$", tail))

    def _extract_shell_prompt_text(self, window):
        tail = window[-500:]
        m = re.search(r"([^\n]*(?:root@pay-(?:if|exp)|pay-(?:if|exp))[^\n]*#\s*)$", tail, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _apply_backspaces(self, text):
        out = []
        for ch in str(text or ""):
            if ch in ("\b", "\x7f"):
                if out:
                    out.pop()
            else:
                out.append(ch)
        return "".join(out)

    def _queue_or_send_repl_command(self, name, cmd):
        pending = self.channel_pending_commands.setdefault(name, [])
        if not self.channel_prompt_ready.get(name, False):
            pending.append(cmd)
            self._emit_log(name, "[SSH] Waiting for >>> prompt before sending command")
            return

        self.channel_prompt_ready[name] = False
        self.channel_partial_prompts[name] = None
        self._send_raw_to_channel(
            name,
            str(cmd) + "\r",
            char_delay=self._COMMAND_CHAR_DELAYS.get(name, 0.0),
        )

    def _handle_runtime_prompt(self, name, line):
        if name == "ttyS2":
            if self._looks_like_mcu_prompt(line):
                self.channel_runtime_modes[name] = "mcu"
                self.channel_prompt_ready[name] = True
                self.channel_partial_prompts[name] = None
            return

        if name != "ttyS5":
            return
        if self._looks_like_shell_prompt(line):
            self.channel_runtime_modes[name] = "shell"
            self.channel_prompt_ready[name] = True
            self.channel_pending_commands[name] = []
            self.channel_partial_prompts[name] = None
            return
        if line.strip() != ">>>":
            return

        self._mark_repl_prompt_ready(name, display_prompt=False)

    def _handle_runtime_partial_prompt(self, name):
        if name == "ttyS2":
            tail = self.buffers.get(name, "")[-500:]
            if not tail:
                return

            mcu_prompt = self._extract_mcu_prompt_text(tail)
            if mcu_prompt:
                key = f"mcu:{mcu_prompt.lower()}"
                if self.channel_partial_prompts.get(name) != key:
                    self._emit_log(name, mcu_prompt)
                    self.channel_partial_prompts[name] = key
                self.channel_runtime_modes[name] = "mcu"
                self.channel_prompt_ready[name] = True
                self.sig_data.emit(mcu_prompt)
                return

            key = self._prompt_key(tail)
            if not key or self.channel_partial_prompts.get(name) == key:
                return

            text = self._partial_prompt_text(tail, key)
            self.channel_partial_prompts[name] = key
            self._emit_log(name, text)
            self.sig_data.emit(text)
            return

        if name != "ttyS5":
            return

        tail = self.buffers.get(name, "")[-120:]
        if tail.strip().endswith(">>>"):
            self._mark_repl_prompt_ready(name, display_prompt=True)
            return

        prompt = self._extract_shell_prompt_text(tail)
        if prompt:
            key = f"shell:{prompt}"
            if self.channel_partial_prompts.get(name) != key:
                self._emit_log(name, prompt)
                self.channel_partial_prompts[name] = key
            self.channel_runtime_modes[name] = "shell"
            self.channel_prompt_ready[name] = True
            self.channel_pending_commands[name] = []

    def _mark_repl_prompt_ready(self, name, display_prompt=False):
        if display_prompt and self.channel_partial_prompts.get(name) != "repl:>>>":
            self._emit_log(name, ">>>")
            self.channel_partial_prompts[name] = "repl:>>>"
        self.channel_runtime_modes[name] = "repl"
        self.channel_prompt_ready[name] = True
        pending = self.channel_pending_commands.get(name) or []
        if pending:
            next_cmd = pending.pop(0)
            self._queue_or_send_repl_command(name, next_cmd)

    def _clear_channel_window(self, name):
        self.buffers[name] = ""
        self.channel_window_histories[name] = ""
        self.channel_rx_line_chars[name] = []
        self.channel_rx_cursors[name] = 0
        self.channel_partial_prompts[name] = None

    def _prompt_key(self, text):
        normalized = re.sub(r"\s+", " ", str(text or "").lower())
        best_prompt = None
        best_pos = -1
        for prompt in self._TTYS2_PARTIAL_PROMPTS:
            pos = normalized.rfind(prompt)
            if pos > best_pos:
                best_prompt = prompt
                best_pos = pos
        return best_prompt if best_pos >= 0 else None

    def _partial_prompt_text(self, text, key):
        clean = self._apply_backspaces(str(text))
        clean = "".join(ch for ch in clean if ch == "\t" or 32 <= ord(ch) <= 126)
        clean = clean.strip()
        if not clean:
            return key

        lower = clean.lower()
        idx = lower.rfind(key)
        if idx >= 0:
            return clean[idx:]
        return clean[-120:]

    def _looks_like_mcu_prompt(self, window):
        tail = window[-500:]
        return bool(re.search(r"(^|\n)[^\n]*debug@mcu:~\s*\$?\s*$", tail.lower()))

    def _extract_mcu_prompt_text(self, window):
        tail = window[-500:]
        m = re.search(r"([^\n]*debug@mcu:~\s*\$?\s*)$", tail, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _emit_synthetic_mcu_prompt(self, name):
        prompt = "DEBUG@MCU:~ $"
        key = f"mcu:{prompt.lower()}"
        if self.channel_partial_prompts.get(name) == key:
            return
        self.channel_partial_prompts[name] = key
        self._emit_log(name, prompt)
        if name == "ttyS2":
            self.sig_data.emit(prompt)


class IFSerialMinicomHandler(QObject):
    """Serial console to IF, then minicom into one IF UART target at a time."""

    sig_log_ttys2 = pyqtSignal(str)
    sig_log_ttys5 = pyqtSignal(str)
    sig_data = pyqtSignal(str)

    _ANSI_RE = SSHMinicomHandler._ANSI_RE
    _MINICOM_NOISE = SSHMinicomHandler._MINICOM_NOISE
    _TARGET_DEVICES = {
        "ttyS2": "/dev/ttyS2",
        "ttyS5": "/dev/ttyS5",
    }
    _EXP_RUNTIME_RE = re.compile(
        r"(?:\bPROFILE=\d+\b.*\bPID:\b|\bSTEP=\S+.*\bPID:\b)",
        re.IGNORECASE,
    )
    _PARTIAL_PROMPTS = (
        "please enter y or n",
        "please entter y or n",
        "profile index:",
        "main ntc:",
        "sec ntc:",
        "tec mask:",
        "heater mask:",
        "setpoint (0.01*c):",
        "main-sec delta (0.01*c):",
        "step count:",
        "step[",
        "save? (y/n):",
        "saved",
    )
    _COMMAND_CHAR_DELAYS = {
        "ttyS2": 0.006,
        "ttyS5": 0.015,
    }

    def __init__(self, log_ttys2_callback, data_callback, log_ttys5_callback=None):
        super().__init__()

        self.ser = None
        self.running = False
        self.active_target = "ttyS2"
        self._pending_target = None
        self._target_baudrate = 115200
        self._minicom_ready = False
        self._bridge_ready = False
        self._in_minicom = False
        self._session_state = "idle"
        self._username = "root"
        self._password = ""
        self._pending_sends = []
        self._last_partial_prompt_key = None
        self._buffer = ""
        self._window = ""
        self._window_history = ""
        self._rx_line_chars = []
        self._rx_cursor = 0
        self._announced_ready_prompt = None
        self._temp_profile_wizard = None
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()

        self.sig_log_ttys2.connect(log_ttys2_callback, Qt.QueuedConnection)
        self.sig_log_ttys5.connect(
            log_ttys5_callback or log_ttys2_callback,
            Qt.QueuedConnection,
        )
        self.sig_data.connect(data_callback, Qt.QueuedConnection)

    def connect(
        self,
        port,
        username="root",
        password="",
        console_baudrate=115200,
        target_baudrate=115200,
        target="ttyS2",
    ):
        if serial is None:
            self.sig_log_ttys2.emit("[IF UART ERROR] pyserial is not installed")
            return False

        try:
            self.disconnect(quiet=True)
            self.active_target = self._normalize_target(target)
            self._pending_target = self.active_target
            self._target_baudrate = int(target_baudrate)
            self._username = username or "root"
            self._password = password or ""
            self._minicom_ready = False
            self._bridge_ready = False
            self._in_minicom = False
            self._session_state = "probe_wait"
            self._pending_sends = []
            self._last_partial_prompt_key = None
            self._buffer = ""
            self._window = ""
            self._window_history = ""
            self._rx_line_chars = []
            self._rx_cursor = 0
            self._announced_ready_prompt = None
            self._temp_profile_wizard = None

            self.ser = serial.Serial(
                port=port,
                baudrate=int(console_baudrate),
                timeout=0.05,
            )
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            self.running = True
            threading.Thread(target=self._read_thread, daemon=True).start()

            self.sig_log_ttys2.emit(
                f"[IF UART] Connected {port} @ {console_baudrate}"
            )
            self.sig_log_ttys2.emit("[IF UART] Probing current IF/UART state")
            self._write_text("\r")
            return True

        except Exception as e:
            self.sig_log_ttys2.emit(f"[IF UART ERROR] {e}")
            self.disconnect(quiet=True)
            return False

    def disconnect(self, quiet=False):
        if self.ser and self._in_minicom:
            self._exit_minicom()
            time.sleep(0.15)

        self.running = False

        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass

        self.ser = None
        self._minicom_ready = False
        self._bridge_ready = False
        self._in_minicom = False
        self._session_state = "idle"
        self._pending_sends = []
        self._last_partial_prompt_key = None
        self._announced_ready_prompt = None
        self._window_history = ""
        self._rx_line_chars = []
        self._rx_cursor = 0
        self._temp_profile_wizard = None

        if not quiet:
            self.sig_log_ttys2.emit("[IF UART] Disconnected")
            self.sig_log_ttys5.emit("[IF UART] Disconnected")

    def send_command(self, cmd):
        if self.active_target != "ttyS2" or not self._minicom_ready:
            self._queue_send("ttyS2", cmd)
            return

        self._send_to_target("ttyS2", cmd)

    def send_ttys5_command(self, cmd):
        if self.active_target != "ttyS5" or not self._minicom_ready:
            self._queue_send("ttyS5", cmd)
            return

        self._send_to_target("ttyS5", cmd)

    def send_interrupt(self):
        if self.active_target != "ttyS2" or not self._minicom_ready:
            self._queue_send("ttyS2", "\x03", raw=True)
            return
        self._send_raw_to_target("ttyS2", "\x03")

    def send_ttys5_interrupt(self):
        if self.active_target != "ttyS5" or not self._minicom_ready:
            self._queue_send("ttyS5", "\x03", raw=True)
            return
        self._send_raw_to_target("ttyS5", "\x03")

    def _queue_send(self, target, cmd, raw=False):
        target = self._normalize_target(target)
        self._pending_sends.append((target, str(cmd), bool(raw)))

        if self.active_target != target or not self._in_minicom:
            self.switch_target(target)

        label = "Ctrl+C" if raw and cmd == "\x03" else cmd
        self._emit_target_log(target, f"[{target}] Queued until minicom READY: {label}")

    def switch_target(self, target, target_baudrate=None):
        target = self._normalize_target(target)
        if target_baudrate is not None:
            self._target_baudrate = int(target_baudrate)

        if target == self.active_target and self._in_minicom:
            return
        if target == self._pending_target and not self._minicom_ready:
            return

        self._pending_target = target
        self._minicom_ready = False
        self._bridge_ready = False
        self._last_partial_prompt_key = None
        self._emit_target_log(target, f"[{target}] Switching IF minicom target")

        if self._in_minicom:
            self._session_state = "exit_wait"
            self._exit_minicom()
        elif self._session_state == "shell_ready":
            self._start_minicom(target)

    def _send_to_target(self, target, cmd):
        if not self._minicom_ready or self.active_target != target:
            self._emit_target_log(target, f"[{target} TX ERROR] minicom is not ready")
            return

        try:
            self._send_raw_to_target(target, str(cmd) + "\r")
        except Exception as e:
            self._emit_target_log(target, f"[{target} TX ERROR] {e}")

    def _send_raw_to_target(self, target, text):
        if not self._minicom_ready or self.active_target != target:
            self._emit_target_log(target, f"[{target} TX ERROR] minicom is not ready")
            return
        self._write_command_text(
            text,
            char_delay=0.0 if text == "\x03" else self._COMMAND_CHAR_DELAYS.get(target, 0.001),
        )

    def _read_thread(self):
        while self.running:
            try:
                if self.ser and self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)
                    if data:
                        self._process_rx(data)
            except Exception as e:
                if self.running:
                    self.sig_log_ttys2.emit(f"[IF UART RX ERROR] {e}")
                break

            time.sleep(0.03)

    def _process_rx(self, data):
        text = data.decode("utf-8", errors="replace")
        text = self._ANSI_RE.sub("", text)
        text = text.replace("\x00", "")

        with self._state_lock:
            lines = []
            idx = 0
            text_len = len(text)
            while idx < text_len:
                ch = text[idx]

                if ch == "\r":
                    if idx + 1 < text_len and text[idx + 1] == "\n":
                        lines.append("".join(self._rx_line_chars))
                        self._window_history = (
                            self._window_history + "".join(self._rx_line_chars) + "\n"
                        )[-5000:]
                        self._rx_line_chars = []
                        self._rx_cursor = 0
                        idx += 2
                        continue

                    # Minicom often redraws the current line with bare CR.
                    # Resetting the visible line here keeps prompts/echoes clean.
                    self._rx_line_chars = []
                    self._rx_cursor = 0
                    idx += 1
                    continue

                if ch == "\n":
                    lines.append("".join(self._rx_line_chars))
                    self._window_history = (
                        self._window_history + "".join(self._rx_line_chars) + "\n"
                    )[-5000:]
                    self._rx_line_chars = []
                    self._rx_cursor = 0
                    idx += 1
                    continue

                if ch in ("\b", "\x7f"):
                    if self._rx_cursor > 0:
                        self._rx_cursor -= 1
                        if self._rx_cursor < len(self._rx_line_chars):
                            self._rx_line_chars.pop(self._rx_cursor)
                    idx += 1
                    continue

                if ch == "\t" or 32 <= ord(ch) <= 126:
                    if self._rx_cursor < len(self._rx_line_chars):
                        self._rx_line_chars[self._rx_cursor] = ch
                    else:
                        self._rx_line_chars.append(ch)
                    self._rx_cursor += 1

                idx += 1

            self._buffer = "".join(self._rx_line_chars)
            self._window = (self._window_history + self._buffer)[-5000:]

        self._handle_session_prompts()

        for raw_line in lines:
            self._handle_line(raw_line)

        self._handle_partial_prompt()

    def _handle_session_prompts(self):
        window = self._get_window()
        lower = window.lower()

        if self._session_state == "probe_wait" and self._looks_like_mcu_prompt(window):
            prompt = self._extract_mcu_prompt_text(window)
            if prompt:
                self._emit_target_rx("ttyS2", prompt)
            self._mark_existing_minicom_ready("ttyS2", "MCU prompt detected")
            return
        if self._session_state == "probe_wait" and self._looks_like_exp_runtime(window):
            self._mark_existing_minicom_ready("ttyS2", "EXP runtime log detected")
            return

        if "login incorrect" in lower:
            self.sig_log_ttys2.emit("[IF UART] Login incorrect detected, retrying username")
            self._clear_window()
            self._session_state = "login_wait"
            self._announced_ready_prompt = None
            self._write_text("\r")
            return

        if self._session_state in ("probe_wait", "login_wait", "password_wait", "shell_wait", "exit_wait"):
            if "password:" in lower:
                self.sig_log_ttys2.emit("[IF UART] Password prompt detected")
                self._write_text(self._password + "\r")
                self._clear_window()
                self._session_state = "shell_wait"
                self._announced_ready_prompt = None
                return

            if "login:" in lower:
                self.sig_log_ttys2.emit("[IF UART] Login prompt detected")
                self._write_text(self._username + "\r")
                self._clear_window()
                self._session_state = "password_wait"
                self._announced_ready_prompt = None
                return

            if self._looks_like_shell_prompt(window):
                prompt = self._extract_shell_prompt_text(window)
                if prompt:
                    self.sig_log_ttys2.emit(prompt)
                self._session_state = "shell_ready"
                self._announced_ready_prompt = None
                self._in_minicom = False
                self._clear_window()
                self._start_minicom(self._pending_target or self.active_target)
                return

        if self._session_state == "probe_wait" and lower.strip().endswith(">"):
            # Unknown prompt style: nudge once more rather than blasting login blindly.
            prompt = lower.strip()[-40:]
            if self._announced_ready_prompt != prompt:
                self.sig_log_ttys2.emit("[IF UART] Unknown prompt detected, waiting for a known login/shell/MCU prompt")
                self._announced_ready_prompt = prompt

    def _mark_existing_minicom_ready(self, target, reason):
        target = self._normalize_target(target)
        self.active_target = target
        self._pending_target = None
        self._in_minicom = True
        self._minicom_ready = True
        self._bridge_ready = True
        self._session_state = "minicom_ready"
        prompt_key = f"{target}:{reason}"
        if self._announced_ready_prompt != prompt_key:
            self._emit_target_log(target, f"[{target}] READY ({reason})")
            self._announced_ready_prompt = prompt_key
        self._clear_window()
        self._flush_pending_sends(target)

    def _start_minicom(self, target):
        target = self._normalize_target(target)
        self.active_target = target
        self._pending_target = None
        self._minicom_ready = False
        self._bridge_ready = False
        self._in_minicom = True
        self._session_state = "minicom_starting"

        device = self._TARGET_DEVICES[target]
        cmd = f"minicom -D {device} -b {int(self._target_baudrate)}"
        self._emit_target_log(target, f"[{target}] {cmd}")
        self._write_text(cmd + "\r")

        threading.Thread(
            target=self._mark_minicom_ready_after_delay,
            args=(target,),
            daemon=True,
        ).start()

    def _mark_minicom_ready_after_delay(self, target):
        time.sleep(1.0)
        if self.running and self._in_minicom and self.active_target == target:
            self._minicom_ready = True
            self._bridge_ready = True
            self._session_state = "minicom_ready"
            self._emit_target_log(target, f"[{target}] READY")
            self._flush_pending_sends(target)

    def _flush_pending_sends(self, target):
        keep = []
        for queued_target, cmd, raw in self._pending_sends:
            if queued_target == target:
                if raw:
                    self._send_raw_to_target(target, cmd)
                else:
                    self._send_to_target(target, cmd)
            else:
                keep.append((queued_target, cmd, raw))
        self._pending_sends = keep

    def _exit_minicom(self):
        try:
            self._clear_window()
            self._write_text("\x01")
            time.sleep(0.08)
            self._write_text("x")
            time.sleep(0.45)
            self._write_text("y")
            time.sleep(0.05)
            self._write_text("\r")
        except Exception:
            pass

    def _handle_line(self, raw_line):
        cleaned = self._apply_backspaces(str(raw_line))
        line = "".join(
            ch for ch in cleaned.strip()
            if ch == "\t" or 32 <= ord(ch) <= 126
        ).strip()

        if not line:
            return

        self._handle_temp_profile_wizard_prompt(line)

        lower = line.lower()
        if any(part in lower for part in self._MINICOM_NOISE):
            return
        if "minicom -d /dev/tty" in lower:
            return
        if self._in_minicom:
            target = self.active_target
            self._emit_target_rx(target, line)
            if target == "ttyS2":
                self.sig_data.emit(line)
                if "unknown command:" in lower or "cancelled" == lower or lower.endswith("cancelled"):
                    self._emit_synthetic_mcu_prompt()
        else:
            self.sig_log_ttys2.emit(line)

        self._last_partial_prompt_key = None

    def _handle_partial_prompt(self):
        if not self._in_minicom:
            return

        with self._state_lock:
            pending = self._buffer[-500:]

        if not pending:
            return

        mcu_prompt = self._extract_mcu_prompt_text(pending)
        if mcu_prompt:
            key = f"mcu:{mcu_prompt.lower()}"
            if key != self._last_partial_prompt_key:
                self._last_partial_prompt_key = key
                target = self.active_target
                self._emit_target_rx(target, mcu_prompt)
                if target == "ttyS2":
                    self.sig_data.emit(mcu_prompt)
            return

        key = self._prompt_key(pending)
        if not key or key == self._last_partial_prompt_key:
            return

        self._last_partial_prompt_key = key
        text = self._partial_prompt_text(pending, key)
        self._handle_temp_profile_wizard_prompt(text)
        target = self.active_target
        self._emit_target_rx(target, text)
        if target == "ttyS2":
            self.sig_data.emit(text)

    def _prompt_key(self, text):
        normalized = re.sub(r"\s+", " ", str(text or "").lower())
        best_prompt = None
        best_pos = -1
        for prompt in self._PARTIAL_PROMPTS:
            pos = normalized.rfind(prompt)
            if pos > best_pos:
                best_prompt = prompt
                best_pos = pos
        return best_prompt if best_pos >= 0 else None

    def _partial_prompt_text(self, text, key):
        clean = self._apply_backspaces(str(text))
        clean = "".join(ch for ch in clean if ch == "\t" or 32 <= ord(ch) <= 126)
        clean = clean.strip()
        if not clean:
            return key

        lower = clean.lower()
        idx = lower.rfind(key)
        if idx >= 0:
            return clean[idx:]
        return clean[-120:]

    def _is_if_shell_noise(self, line):
        if re.search(r"(^|\s)(root@pay-if|pay-if).*[#\$]\s*$", line):
            return True
        if "leave minicom" in line.lower():
            return True
        return False

    def _emit_target_log(self, target, text):
        if target == "ttyS5":
            self.sig_log_ttys5.emit(text)
        else:
            self.sig_log_ttys2.emit(text)

    def _emit_target_rx(self, target, text):
        if target == "ttyS5":
            self.sig_log_ttys5.emit(text)
        else:
            self.sig_log_ttys2.emit(text)

    def _emit_synthetic_mcu_prompt(self):
        prompt = "DEBUG@MCU:~ $"
        key = f"mcu:{prompt.lower()}"
        self._last_partial_prompt_key = key
        self._emit_target_rx("ttyS2", prompt)
        self.sig_data.emit(prompt)

    def _normalize_target(self, target):
        return target if target in self._TARGET_DEVICES else "ttyS2"

    def _write_text(self, text):
        if not self.ser:
            return
        with self._write_lock:
            self.ser.write(text.encode("utf-8", errors="replace"))

    def _write_command_text(self, text, char_delay=0.001):
        if not self.ser:
            return
        with self._write_lock:
            # Gửi toàn bộ text cùng lúc thay vì từng ký tự để tránh mất dữ liệu
            if char_delay <= 0 or text.endswith("\r"):
                # Gửi ngay (REPL command hoặc interrupt)
                self.ser.write(text.encode("utf-8", errors="replace"))
            else:
                # Gửi từng ký tự có delay (cho non-critical commands)
                for ch in text:
                    self.ser.write(ch.encode("utf-8", errors="replace"))
                    if char_delay > 0:
                        time.sleep(char_delay)

    def _get_window(self):
        with self._state_lock:
            return self._window

    def _clear_window(self):
        with self._state_lock:
            self._window = ""
            self._window_history = ""
            self._buffer = ""
            self._rx_line_chars = []
            self._rx_cursor = 0

    def _try_start_temp_profile_wizard(self, cmd):
        text = str(cmd or "").strip()
        if not text.lower().startswith("temp_profile_set"):
            return False

        window = self._get_global_window()
        active_wizard = getattr(window, "_wizard_sm", None) if window else None
        if not active_wizard and re.fullmatch(r"temp_profile_set\s+\d+", text, re.IGNORECASE) is None:
            return False

        ctx = self._build_temp_profile_wizard_context(text)
        if not ctx:
            return False

        if active_wizard and hasattr(active_wizard, "cancel"):
            active_wizard.cancel()

        self._temp_profile_wizard = ctx
        self._send_to_target("ttyS2", "temp_profile_set")
        self._send_to_target("ttyS2", "")
        return True

    def _build_temp_profile_wizard_context(self, cmd_text):
        window = self._get_global_window()
        if window is None:
            return None

        arg_match = re.fullmatch(r"temp_profile_set\s+(\d+)", cmd_text, re.IGNORECASE)

        try:
            pid = int(arg_match.group(1)) if arg_match else int(window.wiz_profile_id.value())
            step_count = int(window.wiz_step_count.value())
            steps = []
            for i in range(step_count):
                start_w, stop_w, dur_w, _ = window._wiz_steps[i]
                start_v = int(round(start_w.value() * 100))
                stop_v = int(round(stop_w.value() * 100))
                dur_v = int(dur_w.value())
                if stop_w.value() > start_w.value():
                    mode_v = 1
                elif stop_w.value() < start_w.value():
                    mode_v = 2
                else:
                    mode_v = 0
                steps.append(f"{start_v} {stop_v} {dur_v} {mode_v}")
        except Exception:
            return None

        return {
            "pid": str(pid),
            "main_ntc": str(int(window.wiz_main_ntc.value())),
            "sec_ntc": str(int(window.wiz_sec_ntc.value())),
            "tec_mask": str(int(window.wiz_tec_mask.value())),
            "heater_mask": str(int(window.wiz_heater_mask.value())),
            "setpoint": str(int(round(window.wiz_setpoint.value() * 100))),
            "delta": str(int(round(window.wiz_delta.value() * 100))),
            "step_count": str(step_count),
            "steps": steps,
            "last_prompt_key": None,
            "last_prompt_ts": 0.0,
            "sent_bootstrap_enter": True,
            "seen_saved": False,
        }

    def _handle_temp_profile_wizard_prompt(self, text):
        ctx = self._temp_profile_wizard
        if not ctx or self.active_target != "ttyS2" or not self._minicom_ready:
            return

        line = str(text or "").strip()
        if not line:
            return

        lower = line.lower()
        now = time.monotonic()

        prompt_key = None
        response = None

        if "debug@mcu" in lower and not ctx["sent_bootstrap_enter"]:
            prompt_key = "bootstrap-enter"
            response = ""
            ctx["sent_bootstrap_enter"] = True
        elif "please enter y or n" in lower or "save? (y/n):" in lower:
            prompt_key = "confirm"
            response = "y"
        elif "profile index:" in lower:
            prompt_key = "profile-index"
            response = ctx["pid"]
        elif "main ntc:" in lower:
            prompt_key = "main-ntc"
            response = ctx["main_ntc"]
        elif "sec ntc:" in lower:
            prompt_key = "sec-ntc"
            response = ctx["sec_ntc"]
        elif "tec mask:" in lower:
            prompt_key = "tec-mask"
            response = ctx["tec_mask"]
        elif "heater mask:" in lower:
            prompt_key = "heater-mask"
            response = ctx["heater_mask"]
        elif "setpoint (0.01*c):" in lower:
            prompt_key = "setpoint"
            response = ctx["setpoint"]
        elif "main-sec delta (0.01*c):" in lower:
            prompt_key = "main-sec-delta"
            response = ctx["delta"]
        elif "step count:" in lower:
            prompt_key = "step-count"
            response = ctx["step_count"]
        else:
            step_match = re.search(r"step\[(\d+)\]:", lower)
            if step_match:
                step_idx = int(step_match.group(1))
                if 0 <= step_idx < len(ctx["steps"]):
                    prompt_key = f"step-{step_idx}"
                    response = ctx["steps"][step_idx]

        if "saved" in lower:
            ctx["seen_saved"] = True

        if ctx["seen_saved"] and "debug@mcu" in lower:
            self._finish_temp_profile_wizard(True, "Profile saved")
            return

        if prompt_key is None or response is None:
            return

        if (
            ctx["last_prompt_key"] == prompt_key
            and now - ctx["last_prompt_ts"] < 0.15
        ):
            return

        ctx["last_prompt_key"] = prompt_key
        ctx["last_prompt_ts"] = now
        self._send_to_target("ttyS2", response)

    def _finish_temp_profile_wizard(self, ok, msg):
        ctx = self._temp_profile_wizard
        self._temp_profile_wizard = None

        window = self._get_global_window()
        if not window:
            return

        try:
            import temp_ctrl
            temp_ctrl._on_wizard_finished(window, ok, msg)
        except Exception:
            if hasattr(window, "_wiz_send_btn"):
                window._wiz_send_btn.setEnabled(True)
            if hasattr(window, "_wiz_cancel_btn"):
                window._wiz_cancel_btn.setVisible(False)

    def _get_global_window(self):
        try:
            import global_var
            return getattr(global_var, "window", None)
        except Exception:
            return None

    def _looks_like_shell_prompt(self, window):
        tail = window[-500:]
        return bool(re.search(r"(^|\n)[^\n]*(root@pay-if|pay-if)[^\n]*#\s*$", tail))

    def _looks_like_mcu_prompt(self, window):
        tail = window[-500:]
        return bool(re.search(r"(^|\n)[^\n]*debug@mcu:~\s*\$?\s*$", tail.lower()))

    def _looks_like_exp_runtime(self, window):
        tail = window[-1200:]
        return bool(self._EXP_RUNTIME_RE.search(tail))

    def _extract_shell_prompt_text(self, window):
        tail = window[-500:]
        m = re.search(r"([^\n]*(?:root@pay-if|pay-if)[^\n]*#\s*)$", tail, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _extract_mcu_prompt_text(self, window):
        tail = window[-500:]
        m = re.search(r"([^\n]*debug@mcu:~\s*\$?\s*)$", tail, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _apply_backspaces(self, text):
        out = []
        for ch in str(text or ""):
            if ch in ("\b", "\x7f"):
                if out:
                    out.pop()
            else:
                out.append(ch)
        return "".join(out)
