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
# class TCPBridgeHandler(QObject):
#     """
#     Thay thế SSHMinicomHandler. 
#     Kết nối trực tiếp tới TCP port đã được socat mở trên Board IF.
#     Loại bỏ hoàn toàn Minicom noise và SSH Shell overhead.
#     """
#     sig_log_ttys2 = pyqtSignal(str)
#     sig_log_ttys5 = pyqtSignal(str)
#     sig_data = pyqtSignal(str)

#     def __init__(self, log_ttys2_callback, data_callback, log_ttys5_callback=None):
#         super().__init__()
#         self.sockets = {}
#         self.running = False
#         self.ser = None # Giữ để tương thích logic main_window

#         self.sig_log_ttys2.connect(log_ttys2_callback, Qt.QueuedConnection)
#         self.sig_log_ttys5.connect(log_ttys5_callback or log_ttys2_callback, Qt.QueuedConnection)
#         self.sig_data.connect(data_callback, Qt.QueuedConnection)

#     def connect(self, host, port_s2=2002, port_s5=2005):
#         try:
#             self.disconnect()
#             self.running = True
#             
#             # Connect ttyS2 bridge
#             s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             s2.connect((host, int(port_s2)))
#             self.sockets["ttyS2"] = s2
#             
#             # Connect ttyS5 bridge
#             s5 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#             s5.connect((host, int(port_s5)))
#             self.sockets["ttyS5"] = s5

#             self.ser = True
#             threading.Thread(target=self._read_thread, args=("ttyS2", s2), daemon=True).start()
#             threading.Thread(target=self._read_thread, args=("ttyS5", s5), daemon=True).start()
#             
#             self.sig_log_ttys2.emit(f"[TCP] Connected to IF Bridge {host}:{port_s2}")
#             return True
#         except Exception as e:
#             self.sig_log_ttys2.emit(f"[TCP ERROR] {e}")
#             return False

#     def disconnect(self):
#         self.running = False
#         for name, s in self.sockets.items():
#             try: s.close()
#             except: pass
#         self.sockets.clear()
#         self.ser = None

#     def send_command(self, cmd):
#         self._send("ttyS2", cmd)

#     def send_ttys5_command(self, cmd):
#         self._send("ttyS5", cmd)

#     def _send(self, name, cmd):
#         s = self.sockets.get(name)
#         if s and self.running:
#             try:
#                 s.sendall((cmd + "\n").encode("utf-8"))
#                 if name == "ttyS2": self.sig_log_ttys2.emit(f"[{name} TX] {cmd}")
#             except Exception as e:
#                 self.sig_log_ttys2.emit(f"[{name} TX ERROR] {e}")

#     def _read_thread(self, name, sock):
#         buffer = ""
#         while self.running:
#             try:
#                 data = sock.recv(4096)
#                 if not data: break
#                 
#                 text = data.decode("utf-8", errors="replace")
#                 buffer += text
#                 while "\n" in buffer:
#                     line, buffer = buffer.split("\n", 1)
#                     line = line.strip()
#                     if not line: continue
#                     
#                     if name == "ttyS2":
#                         self.sig_log_ttys2.emit(f"[{name} RX] {line}")
#                         self.sig_data.emit(line)
#                     else:
#                         self.sig_log_ttys5.emit(f"[{name} RX] {line}")
#             except: break

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

    def __init__(self, log_ttys2_callback, data_callback, log_ttys5_callback=None):
        super().__init__()

        self.client = None
        self.channels = {}
        self.buffers = {}
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

            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
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

            self.running = True
            self._open_minicom_channel("ttyS2", "/dev/ttyS2", baudrate)
            self._open_minicom_channel("ttyS5", "/dev/ttyS5", baudrate)

            self.ser = True
            self.sig_log_ttys2.emit(f"[SSH] Connected {username}@{host}:{ssh_port}")
            self.sig_log_ttys5.emit(f"[SSH] Connected {username}@{host}:{ssh_port}")
            return True

        except Exception as e:
            self.sig_log_ttys2.emit(f"[SSH ERROR] {e}")
            self.sig_log_ttys5.emit(f"[SSH ERROR] {e}")
            self.disconnect(quiet=True)
            return False

    def _open_minicom_channel(self, name, device, baudrate):
        channel = self.client.invoke_shell(term="vt100", width=160, height=48)
        channel.settimeout(0.0)

        self.channels[name] = channel
        self.buffers[name] = ""

        cmd = f"minicom -D {device} -b {int(baudrate)}"
        channel.send(cmd + "\n")
        self._emit_log(name, f"[{name}] {cmd}")

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

        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

        self.client = None
        self.ser = None

        if not quiet:
            self.sig_log_ttys2.emit("[SSH] Disconnected")
            self.sig_log_ttys5.emit("[SSH] Disconnected")

    def send_command(self, cmd):
        self._send_to_channel("ttyS2", cmd, show_tx=True)

    def send_ttys5_command(self, cmd):
        self._send_to_channel("ttyS5", cmd, show_tx=False)

    def _send_to_channel(self, name, cmd, show_tx):
        channel = self.channels.get(name)
        if not self.running or not channel:
            self._emit_log(name, f"[{name} TX ERROR] Not connected")
            return

        try:
            with self._send_lock:
                channel.send(str(cmd) + "\r")
            if show_tx:
                self._emit_log(name, f"[{name} TX] {cmd}")
        except Exception as e:
            self._emit_log(name, f"[{name} TX ERROR] {e}")

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
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        self.buffers[name] = self.buffers.get(name, "") + text

        while "\n" in self.buffers[name]:
            raw_line, self.buffers[name] = self.buffers[name].split("\n", 1)
            self._handle_line(name, raw_line)

    def _handle_line(self, name, raw_line):
        line = "".join(
            ch for ch in raw_line.strip()
            if ch == "\t" or 32 <= ord(ch) <= 126
        ).strip()

        if not line:
            return

        lower = line.lower()
        if any(part in lower for part in self._MINICOM_NOISE):
            return

        self._emit_log(name, f"[{name} RX] {line}")

        if name == "ttyS2":
            self.sig_data.emit(line)

    def _emit_log(self, name, text):
        if name == "ttyS5":
            self.sig_log_ttys5.emit(text)
        else:
            self.sig_log_ttys2.emit(text)
