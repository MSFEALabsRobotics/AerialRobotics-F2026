# Connecting Pi to Pixhawk


<img width="1024" height="576" alt="image" src="https://github.com/user-attachments/assets/01789907-1c76-4dcd-9b09-1ac3615a11fc" />

<img width="228" height="352" alt="image" src="https://github.com/user-attachments/assets/1de2849c-467b-448d-ab41-5a5d4205b9b1" />


Connect a **Raspberry Pi 5 running Ubuntu** to a **Pixhawk 6X running ArduPilot** using **TELEM2**, **MAVLink 2**, and **115200 baud**.

This summarizes our working setup, including the successful Python heartbeat test. Commands run on the Pi unless Windows is explicitly mentioned. These Pi boot settings apply to the Raspberry Pi 5, not Orange Pi boards.

## 1. Hardware and power

- Raspberry Pi 5 with Ubuntu and its USB-C power supply.
- Pixhawk 6X, with a TELEM2 cable.
- Windows laptop with Mission Planner and a USB data cable for the Pixhawk.
- Internet access on the Pi for installing Python packages; the serial connection itself does not need internet.

Keep propellers removed for bench testing. Shut down the Pi and disconnect power from both devices before wiring.

| Pixhawk TELEM2 pin | Signal | Raspberry Pi 5 physical header pin |
|---|---|---|
| 1 | +5 V | Leave disconnected |
| 2 | TX output | **10 — RX / GPIO15** |
| 3 | RX input | **8 — TX / GPIO14** |
| 4 | CTS | Leave disconnected |
| 5 | RTS | Leave disconnected |
| 6 | GND | **6 — GND** |

**TX connects to RX; ground connects to ground.** Both use 3.3 V UART logic.

On an original Holybro cable, the red wire marks pin 1. Verify the connector orientation against the baseboard pinout; the other wires may all be black. Do not assume every black wire is ground.

For this test, power the Pi through its USB-C supply and the Pixhawk through USB from the laptop. The flight battery is not needed. Do not power the Pi from TELEM2.

## 2. Configure the Pixhawk — Windows / Mission Planner

1. Install [Mission Planner](https://ardupilot.org/planner/docs/mission-planner-installation.html), including its device drivers.
2. Connect the Pixhawk to the laptop using USB.
3. Select its **ArduPilot MAVLink COM port**, choose **115200**, and click **CONNECT**. Our port was COM6; yours may differ. Do not select the SLCAN interface.
4. Open **CONFIG → Full Parameter List** and enter:

| Parameter | Value | Purpose |
|---|---:|---|
| `SERIAL2_PROTOCOL` | `2` | MAVLink 2 on TELEM2 |
| `SERIAL2_BAUD` | `115` | 115200 baud |
| `SERIAL2_OPTIONS` | `0` | Normal serial operation |
| `BRD_SER2_RTSCTS` | `0` | Disable hardware flow control |

5. Click **Write Params**, disconnect in Mission Planner, then power-cycle the Pixhawk to apply the settings.

These values are stored on the Pixhawk. Mission Planner does not need to remain open for the Pi to communicate with it.

**Why 115200?** It provides twice the serial bandwidth of 57600 for later telemetry exercises. Both rates work if both ends match. ArduPilot stores 115200 as the parameter value `115`; Python uses the full value `115200`.

## 3. Enable the Pi 5 GPIO UART — Ubuntu

Back up the boot configuration before editing:

```bash
sudo cp -n /boot/firmware/config.txt /boot/firmware/config.txt.before-pixhawk
sudo cp -n /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.before-pixhawk
```

Open the configuration:

```bash
sudo nano /boot/firmware/config.txt
```

If not already present, add at the bottom:

```ini
[all]
dtoverlay=uart0-pi5
```

This enables UART0 on GPIO14 and GPIO15. Save using **Ctrl+O → Enter**, then exit with **Ctrl+X**.

Open the kernel command line:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Remove only this token if present:

```text
console=serial0,115200
```

Keep `console=tty1` and the other existing settings. The whole file must remain **one line**. If `init=/bin/bash` was previously added for password recovery, remove that temporary setting too.

Allow your user to access serial ports, then reboot:

```bash
sudo usermod -aG dialout "$USER"
sudo reboot
```

After logging back in, check:

```bash
ls -l /dev/ttyAMA* /dev/serial*
groups
```

In our working setup:

- **`/dev/ttyAMA0`** is the GPIO UART used for Pixhawk.
- `/dev/ttyAMA10` is the Pi 5 debug UART.
- `/dev/serial*` aliases were absent; this is fine because we use `/dev/ttyAMA0` directly.
- Your groups should include `dialout`.

If `/dev/ttyAMA0` is missing, check the overlay line and reboot before proceeding. Do not substitute the debug UART.

## 4. Optional offline serial test

Use this if the Pi has no internet and Pymavlink is not installed. Power both devices and ensure no other program is reading the GPIO UART.

```bash
stty -F /dev/ttyAMA0 115200 raw -echo -ixon -ixoff -crtscts clocal
timeout 10s dd if=/dev/ttyAMA0 bs=1 count=64 status=none | od -An -tx1
```

- Hexadecimal bytes indicate incoming serial data.
- MAVLink 2 packets begin with `fd`, but seeing `fd` alone does not validate a packet.
- No output within 10 seconds means no bytes were received during the test.

Our captured bytes contained valid MAVLink 2 heartbeat packets. This test checks the **Pixhawk TX → Pi RX** direction.

## 5. Install Pymavlink

With internet available on the Pi:

```bash
sudo apt update
sudo apt install -y python3-venv
python3 -m venv ~/venv-mavlink
source ~/venv-mavlink/bin/activate
python -m pip install pymavlink pyserial
```

In each new terminal, activate the environment before running your scripts:

```bash
source ~/venv-mavlink/bin/activate
```

## 6. Test a MAVLink heartbeat

Paste this entire block into the Pi terminal. It runs directly without creating a Python file:

```bash
MAVLINK20=1 python - <<'PY'
from pymavlink import mavutil

# Open the Pi GPIO UART at the same baud rate as Pixhawk TELEM2.
link = mavutil.mavlink_connection(
    "/dev/ttyAMA0", baud=115200, rtscts=False
)

try:
    print("Waiting for Pixhawk heartbeat...")
    heartbeat = link.wait_heartbeat(timeout=15)

    if heartbeat is None:
        print("No heartbeat received within 15 seconds.")
    else:
        print("Heartbeat received!")
        print("System ID:", heartbeat.get_srcSystem())
        print("Component ID:", heartbeat.get_srcComponent())
        print("Mode:", mavutil.mode_string_v10(heartbeat))
finally:
    link.close()
PY
```

**Success:** `Heartbeat received!` followed by the system ID, component ID, and mode. This was successfully tested on our Pi–Pixhawk setup.

It confirms valid MAVLink reception from the Pixhawk. To verify the reverse direction, the next exercise is to request a parameter from the Pi and receive its reply. A heartbeat test does not establish flight readiness.

## 7. Quick troubleshooting

| Problem | Check |
|---|---|
| `Permission denied` | Run `groups`; confirm `dialout`. Log out/in or reboot after adding the group. |
| `/dev/ttyAMA0` missing | Check `dtoverlay=uart0-pi5` in `/boot/firmware/config.txt`, then reboot. |
| `/dev/serial*` missing | Use `/dev/ttyAMA0` directly, as in our setup. |
| No heartbeat | Check Pixhawk power, TELEM2 selection, crossed TX/RX, common ground, matching baud rate, and saved parameters. |
| `No module named pymavlink` | Activate `~/venv-mavlink`; install packages inside that environment. |
| Package installation fails | Establish Pi internet access; the offline test can still check incoming bytes. |
| Inconsistent serial reads | Ensure only one process reads `/dev/ttyAMA0`; stop other scripts, MAVProxy, or serial monitors. |

## References

- [Holybro Pixhawk baseboard v2 pinout](https://docs.holybro.com/autopilot/pixhawk-baseboards/pixhawk-baseboard-v2-ports)
- [Holybro Pixhawk baseboard v1 pinout](https://docs.holybro.com/autopilot/pixhawk-baseboards/pixhawk-baseboard-v1-ports)
- [ArduPilot Pixhawk 6X UART mapping](https://ardupilot.org/plane/docs/common-holybro-pixhawk6X.html)
- [ArduPilot: Raspberry Pi via MAVLink](https://ardupilot.org/dev/docs/raspberry-pi-via-mavlink.html)
- [Raspberry Pi UART overlay reference](https://raw.githubusercontent.com/raspberrypi/firmware/master/boot/overlays/README)
- [Pymavlink documentation](https://mavlink.io/en/mavgen_python/)
