# temp_ctrl_parser.py
import re
import time
import global_var

from uart_ui import auto_detect_state
from temp_ctrl import (
    update_pid_display,
    pipe_to_response
)
from bmp390 import update_bmp390_ui

# ═══════════════════════════════════════════════════════════════════════════════
# PID REGEX
# ═══════════════════════════════════════════════════════════════════════════════

# FORMAT 1: STEP=NONE | PID: SP=25.00 PV=28.41 OUT=-100.00 ERR=-3.41
_PID_RE_1 = re.compile(
    r"STEP=(\S+)\s*\|\s*PID:\s*"
    r"SP=([+-]?\d+\.\d+)\s+"
    r"PV=([+-]?\d+\.\d+)\s+"
    r"OUT=([+-]?\d+\.\d+)\s+"
    r"ERR=([+-]?\d+\.\d+)"
)

# FORMAT 2: STEP=2 MODE=2 DUR=200 | PID: SP=28.90 PV=26.18 OUT=0.00 ERR=2.72
_PID_RE_2 = re.compile(
    r"STEP=(\d+)\s+MODE=(\d+)\s+DUR=(\d+)\s*\|\s*PID:\s*"
    r"SP=([+-]?\d+\.\d+)\s+"
    r"PV=([+-]?\d+\.\d+)\s+"
    r"OUT=([+-]?\d+\.\d+)\s+"
    r"ERR=([+-]?\d+\.\d+)"
)

_BMP390_CLI_RE = re.compile(
    r"Temp:\s*([+-]?\d+(?:\.\d+)?)\s*C\s+"
    r"Pressure:\s*([+-]?\d+(?:\.\d+)?)\s*Pa",
    re.IGNORECASE
)

MAX_HISTORY = 50000


# ═══════════════════════════════════════════════════════════════════════════════
# PUSH HISTORY (Time-based)
# ═══════════════════════════════════════════════════════════════════════════════

def _push_history():
    """Append PV, thời gian thực và giới hạn history"""
    if not hasattr(global_var, 'pid_start_time') or global_var.pid_start_time is None:
        global_var.pid_start_time = time.time()

    elapsed = time.time() - global_var.pid_start_time

    # Khởi tạo list nếu chưa có
    for var in ['pid_pv_history', 'pid_sp_history', 'pid_err_history', 'pid_time_history']:
        if not hasattr(global_var, var):
            setattr(global_var, var, [])

    global_var.pid_pv_history.append(global_var.pid_pv)
    global_var.pid_sp_history.append(global_var.pid_sp)
    global_var.pid_err_history.append(global_var.pid_err)
    global_var.pid_time_history.append(elapsed)

    # Giới hạn độ dài
    if len(global_var.pid_pv_history) > MAX_HISTORY:
        global_var.pid_pv_history.pop(0)
        global_var.pid_sp_history.pop(0)
        global_var.pid_err_history.pop(0)
        global_var.pid_time_history.pop(0)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_uart_line(line: str):
    line = line.strip()
    if not line:
        return

    # ────────────────────────────────────────────────────────────────────────
    # 0. Pipe to Response Box
    # ────────────────────────────────────────────────────────────────────────
    try:
        if global_var.window:
            pipe_to_response(global_var.window, line)
    except Exception:
        pass

    # ────────────────────────────────────────────────────────────────────────
    # 1. Auto Detect State
    # ────────────────────────────────────────────────────────────────────────
    try:
        if global_var.window:
            auto_detect_state(global_var.window, line)
    except Exception:
        pass

    # ====================== PID FORMAT 1 ======================
    try:
        m = _PID_RE_1.search(line)
        if m:
            global_var.pid_step = m.group(1)

            global_var.pid_sp  = float(m.group(2))
            global_var.pid_pv  = float(m.group(3))
            global_var.pid_out = float(m.group(4))
            global_var.pid_err = float(m.group(5))

            _push_history()

            # Append Target cho đồ thị
            try:
                if hasattr(global_var, 'pid_target_history') is False:
                    global_var.pid_target_history = []
                if hasattr(global_var, 'pid_target_history_time') is False:
                    global_var.pid_target_history_time = []

                step_idx = int(global_var.pid_step) if str(global_var.pid_step).isdigit() else 0

                if (hasattr(global_var.window, "_wiz_steps") and 
                    step_idx < len(global_var.window._wiz_steps)):
                    _, stop_w, _, _ = global_var.window._wiz_steps[step_idx]
                    target = stop_w.value()
                else:
                    target = global_var.pid_sp

                global_var.pid_target_history.append(target)
                global_var.pid_target_history_time.append(
                    time.time() - global_var.pid_start_time
                )
            except:
                pass

            if global_var.window:
                update_pid_display(global_var.window)
            return

    except Exception as e:
        print("PID parse 1 error:", e)

    # ====================== PID FORMAT 2 ======================
    try:
        m = _PID_RE_2.search(line)
        if m:
            step = m.group(1)
            mode = m.group(2)
            mode_name = {"0": "SOAK", "1": "HEAT", "2": "COOL"}.get(mode, "NONE")
            global_var.pid_step = f"{step}:{mode_name}"

            global_var.pid_sp  = float(m.group(4))
            global_var.pid_pv  = float(m.group(5))
            global_var.pid_out = float(m.group(6))
            global_var.pid_err = float(m.group(7))

            _push_history()

            if global_var.window:
                update_pid_display(global_var.window)
            return

    except Exception as e:
        print("PID parse 2 error:", e)

    # ====================== SENSOR PARSERS ======================
    try:
        m = _BMP390_CLI_RE.search(line)
        if m:
            global_var.bmp390_temp = float(m.group(1))
            global_var.bmp390_press = float(m.group(2))
            if global_var.window:
                update_bmp390_ui(
                    global_var.window,
                    global_var.bmp390_temp,
                    global_var.bmp390_press,
                    "Pa"
                )
            return

        if line.startswith("NTC"):
            key, val = line.split(":", 1)
            global_var.ntc_temp[key.strip()] = int(val.strip())

        elif line.startswith("BMP_TEMP"):
            _, val = line.split(":", 1)
            global_var.bmp390_temp = float(val.strip())
            if global_var.window:
                update_bmp390_ui(
                    global_var.window,
                    global_var.bmp390_temp,
                    global_var.bmp390_press,
                    "hPa"
                )

        elif line.startswith("BMP_PRESS"):
            _, val = line.split(":", 1)
            global_var.bmp390_press = float(val.strip())
            if global_var.window:
                update_bmp390_ui(
                    global_var.window,
                    global_var.bmp390_temp,
                    global_var.bmp390_press,
                    "hPa"
                )
    except Exception as e:
        print("Sensor parse error:", e)
