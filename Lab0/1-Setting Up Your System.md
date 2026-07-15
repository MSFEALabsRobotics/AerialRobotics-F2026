# System Architechture


<img width="976" height="551" alt="image" src="https://github.com/user-attachments/assets/f76fc739-809b-4473-9418-6fe07614c0cb" />



# WSL Setup Guide

---

## 🖥️ Install WSL
```bash
wsl --install --no-distribution
```

### In Case WSL could be installed because of virtulization setting, check below troubleshooting to enable it


---

## 📂 Create a New Folder
```bash
mkdir "C:\WSL\MyNewImage"
```

---

## 📦 Import the Tar Image
```bash
wsl --import MyNewImage "FolderPath" "ImagePath"
```

**Example:**
```bash
wsl --import MyNewImage "C:\WSL\MyNewImage" "C:\Users\samer\Documents\AUB\AerialRobotics\mywsl.tar"
```

Check available images:
```bash
wsl --list
```

---

# 🚁 Using Blocks AirSim Environment

## 🔽 Install DirectX Runtime
Download and install from:  
[Microsoft DirectX Runtime](https://www.microsoft.com/en-us/download/details.aspx?id=35)

---

## 📥 Download AirSim Blocks
Get the latest release from:  
[AirSim Releases](https://github.com/microsoft/airsim/releases)

---

## ⚙️ Configure Settings
After running Blocks for the first time, it will create an AirSim settings file in:
```
Documents\AirSim
```

1. Replace this file with the `settings.json` provided in the GitHub repository.  
2. **Inside the settings file**, replace `WINDOWSIP` and `WSLIP` with their correct values.

---

## 🌐 Network Setup
1. **Windows Terminal (not Linux):**  
   Run `ipconfig` to get the **Windows IPv4 Ethernet WSL address**.

2. **WSL (Linux Terminal):**  
   Run:
   ```bash
   ip address show
   ```
   to get the **WSL image IP**.

---

## ▶️ Starting the System
1. Start **AirSim Blocks** in Windows.  
2. Open a new terminal in **WSL (SITL)** and run:

```bash
~/ardupilot/Tools/autotest/sim_vehicle.py -v ArduCopter -f airsim-copter --console --map \ -A "--sim-address=WINDOWSIP --sim-port-in=9002 --sim-port-out=9003"  --out udp:127.0.0.1:14550
```

---

## 📝 Code Editing & Python Scripts

### ✏️ Creating Scripts
- Use **nano** to create/edit a script in WSL:  
  ```bash
  nano scriptname.py
  ```
  - `Ctrl+O` → Save file  
  - `Ctrl+X` → Exit  

- Use **VS Code** (if installed on Windows):  
  ```bash
  code .
  ```
  This will open the editor in the current directory.
---

### ▶️ Running Example Scripts
Run your Hello World scripts separately:
```bash
python3 HelloWorld_AirsimCamera.py
python3 HelloWorld_SITL.py
```

---

## ⚠️ Troubleshooting: Drone Not Arming
If the drone is not arming in SITL, adjust these parameters:

1. In the SITL GUI → go to **Parameters** → **Editor**  
2. Set:
   - `ARMING_CHECK = 0`
   - `EK3_GPS_CHECK = 0`
3. Click **Write** to save settings.

---


---

## ⚠️ Troubleshooting: Binding Error

<img width="441" height="214" alt="Screenshot 2026-07-08 061242" src="https://github.com/user-attachments/assets/c4e064a7-077b-46e4-8bfc-cf0e5b785e1d" />


Restart WSL, with "wsl -shtudown"
Restart Airsim


---


---

## ⚠️ Troubleshooting: Virtulization not enabeled on laptop
<img width="1600" height="1200" alt="image" src="https://github.com/user-attachments/assets/672407d0-3909-4ea2-ada7-844088da4298" />


Check your laptops settings, for going into BIOS and enabeling the parameter

---





