import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "PI"))
from flight_bridge import FlightBridge, _clip, _stick_pwm

def test_clip_inside_range():
    assert _clip(5, 0, 10) == 5

def test_stick_pwm_center():
    assert _stick_pwm(0) == 1500

def test_stick_pwm_boundaries():          # BVA
    assert _stick_pwm(-127) == 1000
    assert _stick_pwm(127) == 2000
    assert _stick_pwm(200) == 2000        # above max -> clipped

def test_throttle_pwm_boundaries():       # BVA
    b = FlightBridge(dry_run=True)
    assert b._throttle_pwm(0) == 1000
    assert b._throttle_pwm(255) == 1500   # safety cap
    assert b._throttle_pwm(300) == 1500   # above max -> clipped

def test_handle_ignores_invalid_values(): # Equivalence Partitioning
    b = FlightBridge(dry_run=True)
    b.handle({"roll": 50, "pitch": "abc", "armed": True})
    assert b.cmd["roll"] == 50            # valid class -> accepted
    assert b.cmd["pitch"] == 0            # invalid class -> ignored
    assert b.want_armed is True

def test_dry_run_telemetry_altitude():
    b = FlightBridge(dry_run=True)
    b.handle({"throttle": 255})
    assert b.telemetry()["alt_cm"] == 300
