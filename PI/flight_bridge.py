"""
flight_bridge.py  -  runs on the Raspberry Pi, next to pi_webrtc_client_video_only.py

Takes the browser's control messages and flies the Pixhawk (ArduCopter) with them,
using the same MAVLink link (/dev/ttyAMA0, 57600) your colleague's scripts tested.

Browser message format (from index.html), ~30 Hz:
  {"roll":-127..127, "pitch":-127..127, "yaw_rate":-127..127, "throttle":0..255, "armed":true/false}
"""
import threading
import time

try:
    from pymavlink import mavutil
except ImportError:                      # lets dry-run work on a laptop
    mavutil = None

# ------------------------------------------------------------------ SETTINGS
PORT = "/dev/ttyAMA0"       # same as colleague's scripts
BAUD = 57600                # same as colleague's scripts
THROTTLE_MAX_PWM = 1500     # SAFETY CAP for first tests (1000 = off, 2000 = full). Raise later.
PITCH_SIGN = -1             # W (forward) = LOWER pwm on ArduCopter. Flip to +1 if reversed.
ROLL_SIGN = 1               # D = right. Flip to -1 if reversed.
YAW_SIGN = 1                # E = yaw right. Flip to -1 if reversed.
COMMAND_TIMEOUT = 0.5       # seconds without browser commands -> LAND
ARM_RETRY_SECONDS = 5       # keep trying to arm this long after you press ARM
SEND_HZ = 20
# ---------------------------------------------------------------------------


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _stick_pwm(v):                  # -127..127 -> 1000..2000
    return int(1500 + _clip(v / 127.0, -1, 1) * 500)


class FlightBridge:
    def __init__(self, port=PORT, baud=BAUD, dry_run=False):
        self.port, self.baud, self.dry_run = port, baud, dry_run
        self.master = None
        self.lock = threading.Lock()
        self.running = False
        self.cmd = {"roll": 0, "pitch": 0, "yaw_rate": 0, "throttle": 0}
        self.want_armed = False
        self.armed = False
        self.last_cmd_time = 0.0
        self.failsafe = False
        self.logged = 0
        self._prev_want = False
        self._arm_until = 0.0
        self._last_arm_try = 0.0
        self.tel = {"roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0,
                    "alt_cm": 0, "battery_v": 0.0}

    # ---------------------------------------------------------------- start/stop
    def start(self):
        if self.dry_run:
            print("[bridge] DRY RUN - nothing is sent to the Pixhawk (fake telemetry)")
        else:
            print(f"[bridge] connecting to Pixhawk {self.port} @ {self.baud} ...")
            self.master = mavutil.mavlink_connection(self.port, baud=self.baud)
            self.master.wait_heartbeat()
            print(f"[bridge] heartbeat from system {self.master.target_system}")
            self.master.mav.request_data_stream_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False
        time.sleep(0.2)
        if self.master:
            self._set_arm(False)
            self._send_rc(0, 0, 0, 0)          # release overrides
            self.master.close()

    # ------------------------------------------------------------ input from browser
    def handle(self, data):
        """Call with the parsed dict the browser sent on the 'control' channel."""
        if self.logged < 3:
            print("[bridge] browser sent:", data)
            self.logged += 1
        with self.lock:
            for k in self.cmd:
                v = data.get(k)
                if isinstance(v, (int, float)):
                    self.cmd[k] = v
            self.want_armed = bool(data.get("armed", False))
            self.last_cmd_time = time.time()

    def telemetry(self):
        t = {"type": "telemetry", "armed": self.armed,
             "failsafe_hold": False, "failsafe_descend": self.failsafe}
        if self.dry_run:                        # same fake numbers as the old demo
            c = self.cmd
            t.update(roll_deg=round(c["roll"] / 127 * 45, 1),
                     pitch_deg=round(c["pitch"] / 127 * 45, 1),
                     yaw_deg=round((c["yaw_rate"] / 127 * 180) % 360, 1),
                     alt_cm=int(c["throttle"] / 255 * 300), battery_v=12.6)
        else:
            t.update(self.tel)
        return t

    # ------------------------------------------------------------------ MAVLink
    def _set_mode(self, name):
        if self.dry_run:
            print(f"[bridge] (dry) mode {name}")
        else:
            self.master.set_mode(self.master.mode_mapping()[name])

    def _set_arm(self, state, force=False):
        if self.dry_run:
            print(f"[bridge] (dry) {'ARM' if state else 'DISARM'}")
            self.armed = state
        else:
            self.master.mav.command_long_send(
                self.master.target_system, self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                1 if state else 0, 21196 if force else 0, 0, 0, 0, 0, 0)

    def _send_rc(self, roll, pitch, thr, yaw):
        if self.master:
            self.master.mav.rc_channels_override_send(
                self.master.target_system, self.master.target_component,
                roll, pitch, thr, yaw, 0, 0, 0, 0)

    def _throttle_pwm(self, thr):               # 0..255 -> 1000..THROTTLE_MAX_PWM
        return int(1000 + _clip(thr / 255.0, 0, 1) * (THROTTLE_MAX_PWM - 1000))

    def _loop(self):
        period = 1.0 / SEND_HZ
        while self.running:
            t0 = time.time()
            with self.lock:
                cmd = dict(self.cmd)
                want = self.want_armed
                stale = self.last_cmd_time > 0 and (t0 - self.last_cmd_time) > COMMAND_TIMEOUT

            # --- link-loss failsafe: LAND, latched until browser sends armed=false
            if stale and self.armed and not self.failsafe:
                print("[bridge] LINK LOST -> LAND")
                self.failsafe = True
                self._set_mode("LAND")
            if not want:
                self.failsafe = False

            # --- ARM button pressed (rising edge): try for a few seconds, then give up.
            #     Never re-arms by itself if the Pixhawk disarms later.
            if want and not self._prev_want:
                self._arm_until = t0 + ARM_RETRY_SECONDS
            self._prev_want = want
            if (want and not self.armed and not self.failsafe and t0 < self._arm_until
                    and cmd["throttle"] <= 10 and t0 - self._last_arm_try > 1.0):
                self._last_arm_try = t0
                self._set_mode("STABILIZE")      # works without GPS, as in colleague's test
                self._set_arm(True)
            elif not want and self.armed:
                self._set_arm(False)

            # --- sticks (neutral + zero throttle unless armed and link ok)
            if self.armed and not self.failsafe:
                self._send_rc(1500 + int(ROLL_SIGN * (_stick_pwm(cmd["roll"]) - 1500)),
                              1500 + int(PITCH_SIGN * (_stick_pwm(cmd["pitch"]) - 1500)),
                              self._throttle_pwm(cmd["throttle"]),
                              1500 + int(YAW_SIGN * (_stick_pwm(cmd["yaw_rate"]) - 1500)))
            else:
                self._send_rc(1500, 1500, 1000, 1500)

            # --- read Pixhawk messages
            if self.master:
                while True:
                    m = self.master.recv_match(blocking=False)
                    if m is None:
                        break
                    ty = m.get_type()
                    if ty == "ATTITUDE":
                        import math
                        self.tel["roll_deg"] = round(math.degrees(m.roll), 1)
                        self.tel["pitch_deg"] = round(math.degrees(m.pitch), 1)
                        self.tel["yaw_deg"] = round(math.degrees(m.yaw) % 360, 1)
                    elif ty == "VFR_HUD":
                        self.tel["alt_cm"] = int(m.alt * 100)
                    elif ty == "SYS_STATUS":
                        self.tel["battery_v"] = round(m.voltage_battery / 1000.0, 1)
                    elif ty == "HEARTBEAT" and m.type != mavutil.mavlink.MAV_TYPE_GCS:
                        self.armed = bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    elif ty == "STATUSTEXT":
                        print("[pixhawk]", m.text)
            time.sleep(max(0, period - (time.time() - t0)))
