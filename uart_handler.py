import serial
import threading
import time

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
