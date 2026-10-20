# Raspberry Pi Companion Computer for AirSim and ArduPilot SITL

## Objectives

Set up a Raspberry Pi to:

1. Run a headless operating system.
2. Receive camera images from AirSim running on Windows.
3. Control an ArduPilot SITL drone using pymavlink.
4. Take off, move forward, hover, and land.

The Raspberry Pi acts as the drone's companion computer.

## 1. System overview

| Device | Software | Role |
|---|---|---|
| Windows PC | AirSim | Simulated environment and cameras |
| WSL Ubuntu on the PC | ArduPilot SITL and MAVProxy | Simulated flight controller and MAVLink routing |
| Raspberry Pi | Raspberry Pi OS Lite and Python | Image acquisition and flight commands |

There are two independent connections:

- **Images:** Raspberry Pi connects to Windows AirSim using TCP port `41451`.
- **Flight control:** MAVProxy sends MAVLink to the Raspberry Pi using UDP port `14550`. The Pi replies through that connection.

Ports `9002` and `9003` belong to the existing AirSim–SITL simulation connection. The Pi does not use them.

### Prerequisite

AirSim and ArduPilot SITL must already work together on the PC.

Use an AirSim vehicle configured as `ArduCopter`, not `SimpleFlight`.

This guide extends that working setup; it does not install AirSim or build SITL.

> Compatibility: the original Microsoft AirSim project and ArduPilot's AirSim integration guide are archived. Keep the AirSim and ArduPilot versions already working in the lab.

> Run the flight examples only with SITL. Disconnect real aircraft from this MAVLink setup.

---

## 2. Install Raspberry Pi OS Lite

Raspberry Pi OS Lite is the headless/server-style edition: it does not include a desktop.

### Download Raspberry Pi Imager

https://www.raspberrypi.com/software/

### Flash the microSD card

1. Insert the microSD card into your computer.
2. Open Raspberry Pi Imager.
3. Select your Raspberry Pi model.
4. Choose **Raspberry Pi OS Lite (64-bit)**.
5. Select the correct microSD card.
6. Configure the OS before writing:

| Setting | Example |
|---|---|
| Hostname | `aerial-pi` |
| Username | `student` |
| Password | Choose your own |
| SSH | Enable |
| Wi-Fi | Enter the lab network credentials, if needed |
| Wi-Fi country | Your actual country; Lebanon is `LB` |
| Time zone | `Asia/Beirut` |

7. Write the image. This erases the selected card.
8. Insert the card into the Pi.
9. Connect Ethernet to the same router as the PC, or use the configured Wi-Fi.
10. Connect the appropriate power supply.

No monitor or keyboard is required when SSH and networking are configured in Imager.

---

## 3. Connect to the Pi

From **Windows PowerShell**:

```powershell
ssh student@aerial-pi.local
```

Replace `student` with your configured username.

If the hostname does not resolve, find the Pi's address in the router's device list:

```powershell
ssh student@192.168.0.60
```

On the **Pi**, display its addresses:

```bash
hostname -I
```

### Example addresses used throughout this guide

| Device/address | Example |
|---|---|
| Windows Wi-Fi/Ethernet IPv4 | `192.168.0.50` |
| Raspberry Pi IPv4 | `192.168.0.60` |
| WSL IPv4 | Separate virtual address; keep your existing SITL configuration |

Replace the example addresses with your actual addresses.

On Windows, use:

```powershell
ipconfig
```

For the Pi's image connection, use the Windows **Wi-Fi or Ethernet IPv4 address**, not its WSL virtual adapter address.

A router DHCP reservation can keep the Pi and Windows addresses consistent.

---

## 4. Install Python packages on the Pi

Run on the **Raspberry Pi**:

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv python3-dev build-essential
```

Create the project and virtual environment:

```bash
mkdir -p ~/aerial_robotics
cd ~/aerial_robotics

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install pymavlink msgpack
```

Verify the imports:

```bash
python -c "from pymavlink import mavutil; import msgpack; print('Packages ready')"
```

Whenever you open a new Pi terminal:

```bash
cd ~/aerial_robotics
source .venv/bin/activate
```

No `--break-system-packages` option is needed.

### Why these packages?

- `pymavlink`: sends commands to ArduPilot and receives telemetry.
- `msgpack`: accesses AirSim's image RPC endpoint through the small helper below.

The image example does not require the `airsim`, `tornado`, or `msgpack-rpc-python` packages.

---

## 5. Allow the Pi to access AirSim images

### 5.1 Update AirSim settings on Windows

Close AirSim.

Open the active `settings.json`, usually:

```text
C:\Users\YOUR_USERNAME\Documents\AirSim\settings.json
```

Add or update these fields at the **top level** of the existing JSON object:

```json
"LocalHostIp": "0.0.0.0",
"ApiServerPort": 41451,
"RpcEnabled": true
```

These are fields to merge into your existing file, not a complete replacement file.

Keep your working `Vehicles` configuration, including:

- `VehicleType: "ArduCopter"`
- Its existing `LocalHostIp` and `UdpIp`
- `UdpPort: 9003`
- `ControlPort: 9002`

The top-level `LocalHostIp` controls the RPC server's listening address. A `LocalHostIp` inside a vehicle configuration belongs to that vehicle's connection.

Check commas carefully when editing JSON.

### 5.2 Allow the image connection through Windows Firewall

Open **PowerShell as Administrator**.

Replace the Pi address below:

```powershell
New-NetFirewallRule -DisplayName "AirSim images from Raspberry Pi" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 41451 -RemoteAddress 192.168.0.60
```

This permits the Pi to reach the image API.

Restart AirSim, then start your existing SITL setup.

### 5.3 Check the connection from the Pi

Run on the **Pi**:

```bash
python -c "import socket; s=socket.create_connection(('192.168.0.50',41451),5); print('AirSim TCP connection OK'); s.close()"
```

Expected:

```text
AirSim TCP connection OK
```

A successful TCP connection verifies network access, but the next step verifies the image API itself.

> Do not add Windows `netsh interface portproxy` rules for MAVLink or simulation UDP ports. That command forwards TCP only.

---

## 6. Receive an AirSim camera image

Raspberry Pi OS Lite has no graphical desktop. This test saves an image on the Pi, which you can copy to Windows.

On the **Pi**:

```bash
cd ~/aerial_robotics
nano get_image.py
```

Paste:

```python
import socket
import time
from pathlib import Path

import msgpack


WINDOWS_IP = "192.168.0.50"  # Windows Wi-Fi/Ethernet address
AIRSIM_PORT = 41451

VEHICLE_NAME = "Copter"     # Exact name under "Vehicles" in settings.json
CAMERA_NAME = "0"
SCENE_IMAGE = 0


def airsim_call(method, *arguments):
    """Make one synchronous MessagePack-RPC request to AirSim."""
    request_id = 1
    request = [0, request_id, method, list(arguments)]

    # raw=True preserves PNG bytes even if encoded as a MessagePack string.
    unpacker = msgpack.Unpacker(
        raw=True,
        max_buffer_size=32 * 1024 * 1024,
    )

    deadline = time.monotonic() + 15

    with socket.create_connection(
        (WINDOWS_IP, AIRSIM_PORT), timeout=5
    ) as connection:
        connection.sendall(msgpack.packb(request, use_bin_type=True))

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("AirSim did not reply within 15 seconds.")

            connection.settimeout(remaining)
            data = connection.recv(65536)

            if not data:
                raise ConnectionError("AirSim closed the connection.")

            unpacker.feed(data)

            for response in unpacker:
                message_type, reply_id, error, result = response

                if message_type != 1 or reply_id != request_id:
                    continue

                if error is not None:
                    raise RuntimeError(f"AirSim RPC error: {error!r}")

                return result


def main():
    print("AirSim ping:", airsim_call("ping"))

    png = airsim_call(
        "simGetImage",
        CAMERA_NAME,
        SCENE_IMAGE,
        VEHICLE_NAME,
        False,  # Camera belongs to the vehicle, not an external camera.
    )

    if not isinstance(png, bytes) or not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(
            "No valid PNG received. Check the vehicle and camera names."
        )

    destination = Path("frame.png")
    destination.write_bytes(png)
    print(f"Saved {destination.resolve()} ({len(png)} bytes)")


if __name__ == "__main__":
    main()
```

Save with **Ctrl+O**, press **Enter**, then exit with **Ctrl+X**.

Run:

```bash
python get_image.py
```

Expected:

```text
AirSim ping: True
Saved /home/student/aerial_robotics/frame.png (... bytes)
```

### View the image on Windows

In a separate **Windows PowerShell** terminal:

```powershell
scp student@192.168.0.60:~/aerial_robotics/frame.png .
Start-Process .\frame.png
```

The image was requested and saved by the Pi.

### Optional: decode the image for computer vision

On the Pi:

```bash
python -m pip install numpy opencv-python-headless
```

Then Python can read the saved image:

```python
import cv2

image = cv2.imread("frame.png")

if image is None:
    raise RuntimeError("Could not read frame.png")

print("Image dimensions:", image.shape)
```

Use `opencv-python-headless` for image processing on the server OS. It does not provide `cv2.imshow()` windows.

---

## 7. Send MAVLink from SITL to the Pi

Keep AirSim and SITL running.

In the **MAVProxy command prompt inside WSL**, enter:

```text
output add 192.168.0.60:14550
set mavfwd True
set streamrate 5
output
```

Replace `192.168.0.60` with the Pi address.

These are MAVProxy commands, not Linux shell commands.

- `output add`: sends MAVLink telemetry to the Pi.
- `mavfwd True`: permits commands from that output client to reach SITL.
- `streamrate 5`: requests telemetry streams at 5 Hz.
- `output`: lists configured destinations.

Add the output once per MAVProxy session. Do not repeatedly add duplicate outputs.

Alternatively, append this option to your existing working `sim_vehicle.py` launch command:

```text
--out=udp:192.168.0.60:14550
```

Keep the rest of your working AirSim/SITL launch options.

### How the return connection works

The Pi listens on UDP port `14550`.

Once MAVProxy sends a packet, pymavlink learns the sender's address and port and sends commands back there.

This also allows a normal WSL NAT setup to initiate the connection outward. Managed networks or additional firewall policies can still block it.

If you have enabled UFW on the Pi, allow the incoming stream:

```bash
sudo ufw allow 14550/udp
```

No Windows UDP portproxy is required.

---

## 8. Test MAVLink reception

On the **Pi**:

```bash
nano test_mavlink.py
```

Paste:

```python
from pymavlink import mavutil


connection = mavutil.mavlink_connection(
    "udpin:0.0.0.0:14550",
    source_system=245,
)

try:
    print("Waiting for ArduPilot heartbeat...")

    heartbeat = connection.recv_match(
        type="HEARTBEAT",
        condition="HEARTBEAT.autopilot == 3",
        blocking=True,
        timeout=20,
    )

    if heartbeat is None:
        raise TimeoutError(
            "No ArduPilot heartbeat. Check MAVProxy output and the Pi IP."
        )

    print("System ID:", heartbeat.get_srcSystem())
    print("Component ID:", heartbeat.get_srcComponent())
    print("Mode:", mavutil.mode_string_v10(heartbeat))

finally:
    connection.close()
```

Run:

```bash
python test_mavlink.py
```

Record the system and component IDs for the flight script.

For a single default SITL vehicle, both are usually `1`.

Close this test before running the flight script. Only one program should listen on this Pi UDP port at a time.

---

## 9. Control the simulated drone with pymavlink

The flight sequence is:

1. Connect to SITL.
2. Enter GUIDED mode.
3. Arm.
4. Take off to 3 m.
5. Move forward at 0.5 m/s for 4 seconds.
6. Hold zero velocity for 2 seconds.
7. Land and wait for disarming.

The forward movement is approximately 2 m; acceleration and braking affect the actual distance.

On the **Pi**:

```bash
nano fly_sitl.py
```

Paste:

```python
import time

from pymavlink import mavutil


# Use the IDs reported by test_mavlink.py.
TARGET_SYSTEM = 1
TARGET_COMPONENT = 1
TAKEOFF_ALTITUDE = 3.0

M = mavutil.mavlink

vehicle = mavutil.mavlink_connection(
    "udpin:0.0.0.0:14550",
    source_system=245,
)

started = time.monotonic()
arm_attempted = False


def wait_for(message_type, predicate, timeout=15):
    """Wait for matching telemetry from our selected flight controller."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        message = vehicle.recv_match(
            type=message_type,
            blocking=True,
            timeout=0.5,
        )

        if message is None:
            continue

        if message.get_srcSystem() != TARGET_SYSTEM:
            continue

        if message.get_srcComponent() != TARGET_COMPONENT:
            continue

        if predicate(message):
            return message

    raise TimeoutError(f"Timed out waiting for {message_type}")


def command(command_id, *parameters):
    """Send COMMAND_LONG and check the corresponding acknowledgment."""
    values = list(parameters) + [0] * (7 - len(parameters))

    vehicle.mav.command_long_send(
        TARGET_SYSTEM,
        TARGET_COMPONENT,
        command_id,
        0,
        *values,
    )

    ack = wait_for(
        "COMMAND_ACK",
        lambda message: message.command == command_id,
    )

    if ack.result != M.MAV_RESULT_ACCEPTED:
        raise RuntimeError(
            f"Command {command_id} was not accepted: result={ack.result}"
        )


def set_mode(name):
    mode_id = vehicle.mode_mapping()[name]

    vehicle.mav.set_mode_send(
        TARGET_SYSTEM,
        M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id,
    )

    wait_for(
        "HEARTBEAT",
        lambda message: message.custom_mode == mode_id,
    )

    print("Mode:", name)


def is_armed(heartbeat):
    return bool(heartbeat.base_mode & M.MAV_MODE_FLAG_SAFETY_ARMED)


def move_body(vx, vy, vz, duration):
    """Body velocities: forward, right, down; units are metres/second."""
    deadline = time.monotonic() + duration

    while time.monotonic() < deadline:
        timestamp = int((time.monotonic() - started) * 1000) & 0xFFFFFFFF

        vehicle.mav.set_position_target_local_ned_send(
            timestamp,
            TARGET_SYSTEM,
            TARGET_COMPONENT,
            M.MAV_FRAME_BODY_NED,
            3527,          # Use velocity; ignore position, acceleration, yaw.
            0, 0, 0,      # Position, ignored.
            vx, vy, vz,   # Velocity.
            0, 0, 0,      # Acceleration, ignored.
            0, 0,         # Yaw and yaw rate, ignored.
        )

        # Read telemetry while maintaining approximately 10 Hz commands.
        interval_end = time.monotonic() + 0.1
        while time.monotonic() < interval_end:
            message = vehicle.recv_match(blocking=False)

            if message is None:
                time.sleep(0.01)
                continue

            if (
                message.get_type() == "HEARTBEAT"
                and message.get_srcSystem() == TARGET_SYSTEM
                and message.get_srcComponent() == TARGET_COMPONENT
                and message.custom_mode != vehicle.mode_mapping()["GUIDED"]
            ):
                raise RuntimeError("Vehicle left GUIDED mode.")


try:
    print("Waiting for SITL...")

    heartbeat = wait_for(
        "HEARTBEAT",
        lambda message: message.autopilot == M.MAV_AUTOPILOT_ARDUPILOTMEGA,
        timeout=20,
    )

    if is_armed(heartbeat):
        raise RuntimeError("Start this exercise with the SITL drone disarmed.")

    # Request position and other standard telemetry streams.
    vehicle.mav.request_data_stream_send(
        TARGET_SYSTEM,
        TARGET_COMPONENT,
        M.MAV_DATA_STREAM_ALL,
        5,
        1,
    )

    set_mode("GUIDED")

    print("Arming...")
    arm_attempted = True
    command(M.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    wait_for("HEARTBEAT", is_armed)

    print(f"Taking off to {TAKEOFF_ALTITUDE} m...")
    command(
        M.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0,
        TAKEOFF_ALTITUDE,
    )

    wait_for(
        "GLOBAL_POSITION_INT",
        lambda message: message.relative_alt / 1000 >= TAKEOFF_ALTITUDE * 0.95,
        timeout=60,
    )

    print("Moving forward...")
    move_body(0.5, 0, 0, 4)

    print("Holding position...")
    move_body(0, 0, 0, 2)

    print("Landing...")
    set_mode("LAND")
    wait_for("HEARTBEAT", lambda message: not is_armed(message), timeout=90)

    arm_attempted = False
    print("Flight complete: vehicle disarmed.")

except (Exception, KeyboardInterrupt) as error:
    print(f"Flight interrupted: {error}")

    if arm_attempted:
        try:
            print("Requesting LAND...")
            set_mode("LAND")
            wait_for(
                "HEARTBEAT",
                lambda message: not is_armed(message),
                timeout=90,
            )
            print("Vehicle disarmed.")
        except (Exception, KeyboardInterrupt) as landing_error:
            print("Could not confirm landing:", landing_error)
            print("Use the MAVProxy console: mode LAND")

finally:
    vehicle.close()
```

Run:

```bash
python fly_sitl.py
```

Watch the simulated drone in AirSim.

### Movement parameters

For the body velocity function:

| Command | Meaning |
|---|---|
| `move_body(0.5, 0, 0, 4)` | Forward for 4 seconds |
| `move_body(-0.5, 0, 0, 4)` | Backward for 4 seconds |
| `move_body(0, 0.5, 0, 4)` | Right for 4 seconds |
| `move_body(0, -0.5, 0, 4)` | Left for 4 seconds |
| `move_body(0, 0, -0.3, 2)` | Up for 2 seconds |
| `move_body(0, 0, 0.3, 2)` | Down for 2 seconds |
| `move_body(0, 0, 0, 2)` | Request zero velocity for 2 seconds |

Positive vertical velocity means **down**.

Velocity commands are repeated at approximately 10 Hz. They are not sent just once.

The script requests landing on an exception or Ctrl+C, but this requires a working connection. It cannot guarantee landing after loss of network or power.

---

## 10. Receive an image during flight

Open a second SSH connection to the Pi.

While `fly_sitl.py` runs in the first terminal, execute:

```bash
cd ~/aerial_robotics
source .venv/bin/activate
python get_image.py
```

Image acquisition and flight control use different network connections and can run together.

Use `scp` again to view the new image on Windows.

---

## 11. Troubleshooting

| Problem | Check |
|---|---|
| Cannot SSH to the Pi | SSH enabled in Imager, correct username/IP, same reachable network |
| TCP 41451 connection refused | AirSim running, RPC enabled, listening address updated |
| TCP connection times out | Windows IP, firewall rule, router client isolation |
| AirSim ping works but no image | Exact vehicle name, camera name, simulation running |
| No MAVLink heartbeat | MAVProxy `output`, correct Pi address, UDP firewall |
| Telemetry arrives but commands do not work | `set mavfwd True`, target IDs, command acknowledgment |
| Arming rejected | Read pre-arm messages in MAVProxy; wait for GPS/EKF readiness |
| Takeoff times out | GUIDED mode, takeoff acknowledgment, position telemetry, AirSim–SITL connection |
| Drone does not move | Vehicle airborne, GUIDED mode, repeated velocity commands |
| `Address already in use` | Stop other Pi programs using UDP 14550 |
| Python package not found | Activate `~/aerial_robotics/.venv` |
| Image display window fails | OS Lite has no desktop; save the PNG and copy it to Windows |

Do not disable arming checks just to hide a connection or estimator problem.

If the Python flight script stops unexpectedly, use the **MAVProxy prompt**:

```text
mode LAND
```

Keep AirSim, SITL, and MAVProxy running until landing is complete.

---

## 12. Normal startup sequence

After the one-time setup:

1. Boot the Raspberry Pi.
2. Start AirSim on Windows.
3. Start your working ArduPilot SITL/MAVProxy setup in WSL.
4. Add the Pi output in MAVProxy:

   ```text
   output add 192.168.0.60:14550
   set mavfwd True
   set streamrate 5
   ```

5. SSH into the Pi:

   ```powershell
   ssh student@192.168.0.60
   ```

6. Activate the environment:

   ```bash
   cd ~/aerial_robotics
   source .venv/bin/activate
   ```

7. Test an image:

   ```bash
   python get_image.py
   ```

8. Test telemetry:

   ```bash
   python test_mavlink.py
   ```

9. Run the simulated flight:

   ```bash
   python fly_sitl.py
   ```

## References

- Raspberry Pi setup:
  https://www.raspberrypi.com/documentation/computers/getting-started.html
- AirSim settings:
  https://microsoft.github.io/AirSim/settings/
- AirSim image client API:
  https://github.com/microsoft/AirSim/blob/main/PythonClient/airsim/client.py
- MessagePack-RPC protocol:
  https://github.com/msgpack-rpc/msgpack-rpc/blob/master/spec.md
- ArduPilot AirSim integration, archived:
  https://ardupilot.org/dev/docs/sitl-with-airsim.html
- MAVProxy telemetry forwarding:
  https://ardupilot.org/mavproxy/docs/getting_started/forwarding.html
- MAVProxy settings:
  https://ardupilot.org/mavproxy/docs/getting_started/settings.html
- ArduPilot GUIDED commands:
  https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html
- Pymavlink:
  https://mavlink.io/en/mavgen_python/
