# 🛩️ Setting up Raspberry Pi for AirSim

This guide explains how to prepare a **Raspberry Pi (Lite or Desktop)** to connect with **AirSim** and process image or MAVLink data.

---

## 1️⃣ Download Required Tools

### 🧰 Raspberry Pi Imager
Download and install the official imager from:  
🔗 [https://www.raspberrypi.com/software/](https://www.raspberrypi.com/software/)

### 💿 Raspberry Pi OS Image
Choose either:
- **Raspberry Pi OS Lite** (for headless setup - Best for performance)
- **Raspberry Pi OS with Desktop** (if you prefer GUI setup - Not for this lab)  
🔗 [https://www.raspberrypi.com/software/operating-systems/](https://www.raspberrypi.com/software/operating-systems/)

---

## 2️⃣ Flash the SD Card

1. Open **Raspberry Pi Imager**  
2. Select the OS and the SD card  
4. Click **Write** to flash the image  
5. Insert the SD card into the Pi

---

## 3️⃣ First Boot

### 1. Connect and start

Connect the following, then power on the Raspberry Pi:
- HDMI display
- Keyboard
- Power supply

Log in using the credentials set in Raspberry Pi Imager:
- **Username:** `pi`
- **Password:** `pi`

### 2. Open configuration

Open a terminal and run:

```bash
sudo raspi-config
```

Configure the following:

| Setting | Menu | Action |
|---|---|---|
| Keyboard | Localisation Options → Keyboard | Select **English (US)** |
| Wi-Fi | System Options → Wireless LAN | Enter your network name (**SSID**) and password |
| SSH | Interface Options → SSH | Select **Yes** to enable remote access |

If prompted for a Wi-Fi country, select the country where you are using the Raspberry Pi.

Select **Finish** and reboot if prompted.

### 3. Find the IP address

Once Wi-Fi is connected, run:

```bash
ip address show
```

Under **`wlan0`**, find the address after `inet`, for example `192.168.1.100`. Ignore the `/24` suffix.

### 4. Connect from your laptop

Connect your laptop to the **same router or phone hotspot** as the Raspberry Pi.

Open a terminal on your laptop and run:

```bash
ssh pi@192.168.1.100
```

Replace `192.168.1.100` with your Raspberry Pi’s IP address.

- Type `yes` if asked to confirm the connection.
- Enter the password: `pi`.
- Password characters will not appear while typing.

---

## 4️⃣ Basic Setup Commands

Update and install Python essentials:
```bash
sudo apt update
sudo apt install python3-pip python3-numpy python3-msgpack python3-setuptools python3-wheel -y
```

---

## 5️⃣ Install Python Packages for AirSim

```bash
pip install numpy msgpack-rpc-python tornado backports.ssl_match_hostname --break-system-packages
pip install --no-build-isolation airsim --break-system-packages
sudo apt install -y libgl1 libglib2.0-0
```

---

## 6️⃣ Optional: pymavlink for MAVLink Communication

```bash
pip3 install pymavlink --break-system-packages
```

---

## 7️⃣ Allow Windows ↔ Pi Network Communication

### 1. Find your Windows Wi-Fi IP address

On **Windows**, open Command Prompt and run:

```cmd
ipconfig
```

Under **Wireless LAN adapter Wi-Fi**, find the **IPv4 Address**, for example `192.168.41.100`.

> Use the **Windows Wi-Fi IP**, not the WSL or virtual adapter IP.

### 2. Ping Windows from the Raspberry Pi

Make sure both devices are connected to the **same router or phone hotspot**.

On the **Raspberry Pi**, run:

```bash
ping -c 4 192.168.41.100
```

Replace `192.168.41.100` with your Windows Wi-Fi IP address.

### 3. If the ping fails, allow it through Windows Firewall

On **Windows**, open **Command Prompt as Administrator** and run:

```cmd
netsh advfirewall firewall add rule name="Allow ICMPv4 In" protocol=icmpv4:8,any dir=in action=allow
```

Then repeat the ping from the Raspberry Pi.


---

## 8️⃣ Use Scripts From Lab0

Use the Python scripts provided in **Lab0** to:

1. Get an image from **AirSim** on the Raspberry Pi.
2. Drive the motor in the simulator from the Raspberry Pi.

### Create and run each script

1. On the **Raspberry Pi**, create a Python file using `nano`:
   ```bash
   nano filename.py
   ```
   Replace `filename.py` with the name of the script.

2. Paste the corresponding **Lab0 Python code** into the file.

3. Save and exit:
   - Press **Ctrl + O**, then **Enter** to save.
   - Press **Ctrl + X** to exit.

4. Run the script:
   ```bash
   python3 filename.py
   ```

---

