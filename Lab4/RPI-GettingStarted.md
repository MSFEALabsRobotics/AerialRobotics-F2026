# Raspberry Pi + AirSim + ArduPilot SITL

## Goals

- Install a headless Raspberry Pi OS.
- Get a camera image from AirSim on Windows.
- Control the simulated drone using pymavlink.

**Before starting:** AirSim and ArduPilot SITL must already work together on your Windows/WSL computer. Use an `ArduCopter` vehicle.

| Device | Example IP | Runs |
|---|---|---|
| Windows PC | `192.168.0.50` | AirSim |
| WSL on the PC | Keep existing configuration | SITL + MAVProxy |
| Raspberry Pi | `192.168.0.60` | Python scripts |

Replace the example IP addresses with your own. Connect the Pi and PC to the same network.

---

## 1. Install Raspberry Pi OS

Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

1. Select your Raspberry Pi model.
2. Select **Raspberry Pi OS Lite (64-bit)**.
3. Select the microSD card.
4. Configure:
   - Hostname: `aerial-pi`
   - Username: `student`
   - Your password
   - Enable SSH
   - Wi-Fi credentials, if needed
   - Your actual Wi-Fi country: `LB` for Lebanon
5. Write the image, insert the card, and power on the Pi.

**Lite is the server-style version without a desktop.**

From Windows PowerShell:

```powershell
ssh student@aerial-pi.local
```

If the hostname fails, use the Pi's IP from your router:

```powershell
ssh student@192.168.0.60
```

---

## 2. Install Python packages

Run on the **Pi**:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev build-essential

mkdir -p ~/aerial_robotics
cd ~/aerial_robotics

python3 -m venv .venv
source .venv/bin/activate

pip install pymavlink msgpack
```

In every new Pi terminal, run:

```bash
cd ~/aerial_robotics
source .venv/bin/activate
```

---

## 3. Enable AirSim image access

On **Windows**, close AirSim and open:

```text
C:\Users\YOUR_USERNAME\Documents\AirSim\settings.json
```

Add/update these fields at the **top level** of the existing JSON:

```json
"LocalHostIp": "0.0.0.0",
"ApiServerPort": 41451,
"RpcEnabled": true
```

Keep the existing `Vehicles` section and its working SITL settings. Check the commas.

Open **PowerShell as Administrator** and allow the Pi:

```powershell
New-NetFirewallRule -DisplayName "AirSim Raspberry Pi" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 41451 -RemoteAddress 192.168.0.60
```

Restart AirSim and your existing SITL setup.

---

## 4. Get an image on the Pi

On the **Pi**:

```bash
nano get_image.py
```

Paste:

```python
import socket
from pathlib import Path
import msgpack

WINDOWS_IP = "192.168.0.50"
VEHICLE = "Copter"  # Exact name under "Vehicles" in settings.json

# Request camera 0, scene image, from the selected vehicle.
request = [0, 1, "simGetImage", ["0", 0, VEHICLE, False]]
decoder = msgpack.Unpacker(raw=True)

with socket.create_connection((WINDOWS_IP, 41451), timeout=15) as sock:
    sock.sendall(msgpack.packb(request, use_bin_type=True))

    while True:
        data = sock.recv(65536)
        if not data:
            raise ConnectionError("AirSim disconnected.")

        decoder.feed(data)

        for reply in decoder:
            message_type, request_id, error, image = reply

            if message_type != 1 or request_id != 1:
                continue
            if error is not None:
                raise RuntimeError(error)
            if not isinstance(image, bytes) or not image.startswith(b"\x89PNG"):
                raise RuntimeError("No image. Check vehicle and camera names.")

            Path("frame.png").write_bytes(image)
            print("Saved frame.png")
            raise SystemExit
```

Save with **Ctrl+O**, **Enter**, then **Ctrl+X**.

Run:

```bash
python get_image.py
```

This small client gets the image directly from AirSim without installing the older `airsim` Python package.

### View the image

In **Windows PowerShell**:

```powershell
scp student@192.168.0.60:~/aerial_robotics/frame.png .
Start-Process .\frame.png
```

---

## 5. Connect SITL to the Pi

In the **MAVProxy prompt inside WSL**, enter:

```text
output add 192.168.0.60:14550
set mavfwd True
set streamrate 5
```

Enter these once per MAVProxy session.

- Telemetry goes to the Pi on UDP `14550`.
- The Pi sends commands back through the same connection.
- No Windows `portproxy` commands are needed.
- Keep ports `9002` and `9003` for your existing AirSim–SITL connection.

---

## 6. Fly the simulated drone

**SITL only. Start with the drone disarmed and no real aircraft connected.**

On the **Pi**:

```bash
nano fly_sitl.py
```

Paste:

```python
import time
from pymavlink import mavutil

M = mavutil.mavlink
drone = mavutil.mavlink_connection(
    "udpin:0.0.0.0:14550", source_system=245
)


def wait_for(kind, condition, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        msg = drone.recv_match(type=kind, blocking=True, timeout=1)
        if (
            msg
            and msg.get_srcSystem() == drone.target_system
            and msg.get_srcComponent() == drone.target_component
            and condition(msg)
        ):
            return msg
    raise TimeoutError(f"Timed out waiting for {kind}")


def mode(name):
    mode_id = drone.mode_mapping()[name]
    drone.set_mode(mode_id)
    wait_for("HEARTBEAT", lambda m: m.custom_mode == mode_id)
    print("Mode:", name)


def armed(msg):
    return bool(msg.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED)


def velocity(vx, vy, vz, seconds):
    # Body frame: +X forward, +Y right, +Z down.
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        drone.mav.set_position_target_local_ned_send(
            0, drone.target_system, drone.target_component,
            M.MAV_FRAME_BODY_NED,
            3527,           # Use velocity only.
            0, 0, 0,       # Position ignored.
            vx, vy, vz,
            0, 0, 0,       # Acceleration ignored.
            0, 0,          # Yaw and yaw rate ignored.
        )
        time.sleep(0.1)


arm_attempted = False

try:
    print("Waiting for SITL heartbeat...")
    hb = drone.wait_heartbeat(timeout=20)
    if hb is None:
        raise TimeoutError("No heartbeat. Check MAVProxy output.")
    if hb.autopilot != M.MAV_AUTOPILOT_ARDUPILOTMEGA:
        raise RuntimeError("Expected an ArduPilot flight controller.")
    if armed(hb):
        raise RuntimeError("Start with the simulated drone disarmed.")

    drone.mav.request_data_stream_send(
        drone.target_system, drone.target_component,
        M.MAV_DATA_STREAM_ALL, 5, 1,
    )

    mode("GUIDED")

    print("Arming...")
    arm_attempted = True
    drone.arducopter_arm()
    wait_for("HEARTBEAT", armed)

    print("Taking off to 3 metres...")
    drone.mav.command_long_send(
        drone.target_system, drone.target_component,
        M.MAV_CMD_NAV_TAKEOFF, 0,
        0, 0, 0, 0, 0, 0, 3,
    )
    wait_for(
        "GLOBAL_POSITION_INT",
        lambda m: m.relative_alt >= 2850,
        timeout=60,
    )

    print("Moving forward...")
    velocity(0.5, 0, 0, 4)

    print("Hovering...")
    velocity(0, 0, 0, 2)

    mode("LAND")
    wait_for("HEARTBEAT", lambda m: not armed(m), timeout=90)
    arm_attempted = False
    print("Landed and disarmed.")

except (Exception, KeyboardInterrupt) as error:
    print("Stopped:", error)
    if arm_attempted:
        try:
            mode("LAND")
            print("LAND requested. Watch the simulator until touchdown.")
        except Exception:
            print("Use MAVProxy: mode LAND")

finally:
    drone.close()
```

Run:

```bash
python fly_sitl.py
```

The drone should:

1. Take off to **3 m**.
2. Move forward at **0.5 m/s for 4 seconds**.
3. Hover for **2 seconds**.
4. Land.

The exception handler requests LAND if the connection still works. It cannot guarantee landing after a lost connection.

### Change the movement

| Function call | Movement |
|---|---|
| `velocity(0.5, 0, 0, 4)` | Forward |
| `velocity(-0.5, 0, 0, 4)` | Backward |
| `velocity(0, 0.5, 0, 4)` | Right |
| `velocity(0, -0.5, 0, 4)` | Left |
| `velocity(0, 0, -0.3, 2)` | Up |
| `velocity(0, 0, 0.3, 2)` | Down |

To capture an image during flight, run `get_image.py` in a second Pi terminal.

---

## Quick troubleshooting

| Problem | Check |
|---|---|
| No image | Windows IP, TCP 41451 firewall rule, vehicle name |
| No heartbeat | MAVProxy output points to the Pi's current IP |
| Telemetry but no control | `set mavfwd True` |
| Arming/takeoff fails | Read MAVProxy pre-arm messages; wait for GPS/EKF readiness |
| Port already in use | Close other Pi MAVLink scripts |
| Need to land manually | Enter `mode LAND` in MAVProxy |

These scripts are tutorial examples and have not been tested against your particular AirSim/SITL installation.
