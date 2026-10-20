# Runs a REAL flight immediately: start disarmed, outdoors with GPS/EKF ready.
# RC pilot ready; onboard failsafes already configured. Run only one script.
import os
import time
os.environ["MAVLINK20"] = "1"
from pymavlink import mavutil

# 1. Same Pi/Pixhawk serial connection as the heartbeat test.
master = mavutil.mavlink_connection(
    "/dev/ttyAMA0", baud=115200, rtscts=False,
    source_system=245, source_component=191)  # Match your GCS-failsafe setup.
hb = master.wait_heartbeat(timeout=15)
if hb is None:
    raise RuntimeError("No heartbeat. Check connection.")
if hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
    raise RuntimeError("Start with the drone disarmed.")
print("Connected:", master.target_system, master.target_component)
last_hb, hb_time, sent_time = hb, time.monotonic(), 0
watch_guided, arm_requested = False, False

# Read telemetry and send our heartbeat while waiting or moving.
def update():
    global last_hb, hb_time, sent_time
    if time.monotonic() - sent_time >= 1:
        master.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS,
                                 mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        sent_time = time.monotonic()
    msg = master.recv_match(blocking=True, timeout=0.1)
    if msg and (msg.get_srcSystem(), msg.get_srcComponent()) != (master.target_system, master.target_component):
        msg = None
    if msg and msg.get_type() == "HEARTBEAT":
        last_hb, hb_time = msg, time.monotonic()
    if watch_guided and mavutil.mode_string_v10(last_hb) != "GUIDED":
        raise RuntimeError("Mode changed: stopping script commands for pilot/failsafe.")
    if time.monotonic() - hb_time > 3:
        raise RuntimeError("Heartbeat lost: pilot take control.")
    return msg

def wait_for(kind, condition, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        msg = update()
        if msg and msg.get_type() == kind and condition(msg):
            return msg
    raise RuntimeError("Timeout waiting for " + kind)

def pause(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        update()

# Send a MAVLink command; unused parameters are filled with zeros.
def command(number, *params):
    master.mav.command_long_send(master.target_system, master.target_component,
                                number, 0, *(list(params) + [0] * (7-len(params))))



try:
    # 2. Enter GUIDED, arm normally, and confirm both using heartbeat messages.
    master.set_mode("GUIDED")
    wait_for("HEARTBEAT", lambda m: mavutil.mode_string_v10(m) == "GUIDED", 8)
    watch_guided = True
    arm_requested = True
    command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    wait_for("HEARTBEAT", lambda m: m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED, 10)

    # 3. Request altitude telemetry, take off to 2 m above home, then hover.
    command(mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 33, 200000)  # GLOBAL_POSITION_INT, 5 Hz
    print("Taking off to 2 m")
    command(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 2)
    wait_for("GLOBAL_POSITION_INT", lambda m: m.relative_alt / 1000 >= 1.9, 30)
    pause(3)

    # 4. Hover for 5 more seconds.
    pause(5)

    # 5. LAND at the current location; let Pixhawk disarm after landing.
    print("Landing")
    watch_guided = False
    master.set_mode("LAND")
    wait_for("HEARTBEAT", lambda m: mavutil.mode_string_v10(m) == "LAND", 8)
    wait_for("HEARTBEAT", lambda m: not (m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED), 120)
    print("Disarmed after LAND")
except (Exception, KeyboardInterrupt) as error:
    print("Stopped:", error, "- pilot verify aircraft/control.")
    # Best effort only: do not overwrite an observed pilot/failsafe mode change.
    if arm_requested and time.monotonic() - hb_time < 3 and mavutil.mode_string_v10(last_hb) == "GUIDED":
        master.set_mode("LAND")
        print("LAND requested; pilot must verify landing.")
finally:
    master.close()
