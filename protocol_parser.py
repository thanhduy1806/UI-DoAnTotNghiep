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

_PROFILE_PID_RE = re.compile(
    r"PROFILE=(\d+)\s+"
    r"STEP=(\S+)"
    r"(?:\s+MODE=(\d+)\s+DUR=(\d+))?"
    r"\s*\|\s*PID:\s*"
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

_PHOTO_CURRENT_RE = re.compile(
    r"(?:PHOTO|PD|PHOTODIODE)"
    r"(?:\s*(?:POS|CH|CHANNEL|IDX|INDEX|#)?\s*[=:]?\s*)"
    r"(\d{1,2})"
    r".*?"
    r"(?:I|CUR|CURRENT|ADC)?\s*[=:]?\s*"
    r"([+-]?\d+(?:\.\d+)?)\s*(nA|uA|µA|mA|A)?",
    re.IGNORECASE,
)

_EXP_DONE_CURRENT_RE = re.compile(
    r"EXP\s+DONE!\s+Current:\s*([+-]?\d+(?:\.\d+)?)\s*(nA|uA|ÂµA|mA|A)?",
    re.IGNORECASE,
)

MAX_HISTORY = 50000


# ═══════════════════════════════════════════════════════════════════════════════
# PUSH HISTORY (Time-based)
# ═══════════════════════════════════════════════════════════════════════════════

def _push_history():
    """Append PV, thời gian thực và giới hạn history"""
    if not getattr(global_var, "pid_graph_session_active", False):
        return

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

def _ensure_profile_history():
    defaults = {
        "pid_profile_time_history": {i: [] for i in range(8)},
        "pid_profile_pv_history": {i: [] for i in range(8)},
        "pid_profile_sp_history": {i: [] for i in range(8)},
        "pid_profile_err_history": {i: [] for i in range(8)},
        "pid_profile_out_history": {i: [] for i in range(8)},
        "pid_profile_latest": {
            i: {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0}
            for i in range(8)
        },
    }
    for name, value in defaults.items():
        if not hasattr(global_var, name):
            setattr(global_var, name, value)
        for i in range(8):
            if name == "pid_profile_latest":
                getattr(global_var, name).setdefault(
                    i, {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0}
                )
            else:
                getattr(global_var, name).setdefault(i, [])


def _push_profile_history(profile_id, sp, pv, out, err):
    if not getattr(global_var, "pid_graph_session_active", False):
        return

    if not hasattr(global_var, 'pid_start_time') or global_var.pid_start_time is None:
        global_var.pid_start_time = time.time()

    elapsed = time.time() - global_var.pid_start_time
    _ensure_profile_history()

    global_var.pid_profile_time_history[profile_id].append(elapsed)
    global_var.pid_profile_pv_history[profile_id].append(pv)
    global_var.pid_profile_sp_history[profile_id].append(sp)
    global_var.pid_profile_err_history[profile_id].append(err)
    global_var.pid_profile_out_history[profile_id].append(out)

    if len(global_var.pid_profile_pv_history[profile_id]) > MAX_HISTORY:
        global_var.pid_profile_time_history[profile_id].pop(0)
        global_var.pid_profile_pv_history[profile_id].pop(0)
        global_var.pid_profile_sp_history[profile_id].pop(0)
        global_var.pid_profile_err_history[profile_id].pop(0)
        global_var.pid_profile_out_history[profile_id].pop(0)


def _selected_profile_id():
    try:
        if global_var.window and hasattr(global_var.window, "tc_run_profile_id"):
            return global_var.window.tc_run_profile_id.value()
    except Exception:
        pass
    return 0


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

    # ====================== PROFILE PID FORMAT ======================
    try:
        m = _PROFILE_PID_RE.search(line)
        if m:
            profile_id = int(m.group(1))
            if not 0 <= profile_id < 8:
                return
            step = m.group(2)
            mode = m.group(3)
            sp = float(m.group(5))
            pv = float(m.group(6))
            out = float(m.group(7))
            err = float(m.group(8))

            _push_profile_history(profile_id, sp, pv, out, err)
            if mode is not None:
                mode_name = {"0": "SOAK", "1": "HEAT", "2": "COOL"}.get(mode, "NONE")
                step_text = f"{step}:{mode_name}"
            else:
                step_text = step

            global_var.pid_profile_latest[profile_id] = {
                "step": step_text,
                "sp": sp,
                "pv": pv,
                "err": err,
                "out": out,
            }

            if profile_id == _selected_profile_id():
                global_var.pid_step = step_text
                global_var.pid_sp = sp
                global_var.pid_pv = pv
                global_var.pid_out = out
                global_var.pid_err = err

            if global_var.window:
                update_pid_display(global_var.window)
            return

    except Exception as e:
        print("Profile PID parse error:", e)

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

    # ====================== EXP LASER CURRENT FORMAT ======================
    try:
        m = _EXP_DONE_CURRENT_RE.search(line)
        if m:
            value = float(m.group(1))
            unit = (m.group(2) or "A").replace("Âµ", "u")
            if global_var.window:
                pos = getattr(global_var.window, "_manual_running_laser_pos", None)
                if pos is None:
                    pos = getattr(global_var.window, "_manual_selected_laser_pos", None)
                if isinstance(pos, int) and 1 <= pos <= 24:
                    from exp_manual import update_photo_current
                    display_value = f"{m.group(1)} {unit}" if unit else m.group(1)
                    update_photo_current(global_var.window, pos, display_value)
            return

        if re.fullmatch(r"EXP\s+DONE!", line, re.IGNORECASE):
            if global_var.window:
                from exp_manual import clear_gui_laser_exp_pending, consume_gui_laser_exp_pending, finish_laser_experiment
                if consume_gui_laser_exp_pending(global_var.window):
                    if hasattr(global_var.window, "uart") and global_var.window.uart:
                        global_var.window.uart.send_command("exp_end")
                        clear_gui_laser_exp_pending(global_var.window)
                finish_laser_experiment(global_var.window)
            return
    except Exception as e:
        print("EXP laser parse error:", e)

    # ====================== PHOTO CURRENT FORMAT ======================
    try:
        m = _PHOTO_CURRENT_RE.search(line)
        if m:
            pos = int(m.group(1))
            if 1 <= pos <= 24:
                value = float(m.group(2))
                unit = (m.group(3) or "").replace("µ", "u")
                if not hasattr(global_var, "photo_current"):
                    global_var.photo_current = {i: None for i in range(1, 25)}
                global_var.photo_current[pos] = f"{value:g}{unit}" if unit else value
                if global_var.window:
                    from exp_manual import update_photo_current
                    update_photo_current(global_var.window, pos, global_var.photo_current[pos])
            return
    except Exception as e:
        print("PHOTO parse error:", e)

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
