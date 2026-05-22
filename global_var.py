# global_var.py
# Thêm các biến PID vào file global_var hiện có của bạn
# Nếu đã có ntc_temp, bmp390_temp, bmp390_press thì chỉ cần thêm phần PID

window = None

# ── Sensor data (giữ nguyên cũ) ──────────────────────────────────────────────
ntc_temp     = {}       # {"NTC1": 2841, "NTC2": ...}  (x100 °C)
bmp390_temp  = 0
bmp390_press = 0

# ── PID realtime (thêm mới) ───────────────────────────────────────────────────
pid_step = "NONE"       # tên bước hiện tại: NONE / HEAT / COOL / SOAK / ...
pid_sp   = 0.0          # setpoint (°C)
pid_pv   = 0.0          # process value – nhiệt độ đo được (°C)
pid_out  = 0.0          # output PID (-100 … +100)
pid_err  = 0.0          # error = PV - SP

# History cho graph (tối đa 300 điểm)
pid_graph_session_active = False
pid_sp_history  = []
pid_pv_history  = []
pid_err_history = []
pid_time_history = []

# History riêng cho 8 profile auto: {0: [...], 1: [...], ...}
pid_profile_time_history = {i: [] for i in range(8)}
pid_profile_pv_history = {i: [] for i in range(8)}
pid_profile_sp_history = {i: [] for i in range(8)}
pid_profile_err_history = {i: [] for i in range(8)}
pid_profile_out_history = {i: [] for i in range(8)}
pid_profile_latest = {
    i: {"step": "NONE", "sp": 0.0, "pv": 0.0, "err": 0.0, "out": 0.0}
    for i in range(8)
}

laser_drive_current = {i: None for i in range(1, 25)}
photo_current = {i: None for i in range(1, 25)}

# Target profile lookup table (full pre-computed, revealed per sample)
pid_target_lookup   = []   # toàn bộ profile tính sẵn khi nhấn START
pid_target_history  = []   # phần đã reveal theo sample thực tế
