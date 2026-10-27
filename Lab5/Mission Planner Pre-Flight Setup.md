# Mission Planner Pre-Flight Setup
**Holybro Quad — ArduCopter**

Initial setup before first takeoff; repeat relevant checks after hardware or configuration changes.

## 0) Safety
- [ ] **Props OFF** for all calibrations and motor tests.
- [ ] Battery secured; no loose cables; frame rigid.

## 1) Frame & Firmware
- [ ] Connect via USB → load ArduCopter if needed → Connect.
- [ ] **Frame Type:** `FRAME_CLASS = 1 (Quad)`; `FRAME_TYPE = 1 (X)`.
- [ ] Write parameters; reboot if prompted.

## 2) Accelerometer
- [ ] **Mandatory Hardware → Accel Calibration.**
- [ ] Run **Calibrate Accelerometer**, following each orientation: level, left, right, nose down, nose up, upside down.
- [ ] Keep the aircraft still at each step; confirm success.
- [ ] Use **Calibrate Level** with the mounted airframe level, if needed.

## 3) Compass
- [ ] **Mandatory Hardware → Compass.**
- [ ] Calibrate outdoors, away from metal and electrical interference, with a good GPS fix.
- [ ] Run **Onboard Mag Calibration**; confirm success and reboot.
- [ ] Disable compass #3 only if faulty or affected by interference, with another healthy compass available.

## 4) RC Calibration & Throttle Failsafe
- [ ] **Mandatory Hardware → Radio Calibration.**
- [ ] Move all sticks/switches through their full range → Done.
- [ ] Configure receiver signal-loss behavior. If using low-throttle failsafe, set loss output to approximately **960 µs**.
- [ ] Set `FS_THR_VALUE` between the loss PWM and normal minimum throttle.
- [ ] Set `FS_THR_ENABLE = 1` (**RTL**, with Land fallback).
- [ ] Verify `RC3_MIN/MAX` if throttle uses RC3; save.
- [ ] **Props-off test:** turn off TX and confirm failsafe detection. When armed on the ground, the aircraft may disarm instead of entering RTL. Restore TX; disarm.

## 5) Motor Outputs & Motor Test
- [ ] Verify outputs 1–4 are assigned to Motors 1–4.
- [ ] **Optional Hardware → Motor Test.**
- [ ] Release the hardware safety switch if required.
- [ ] Briefly test each motor; verify position and rotation against the selected frame diagram.
- [ ] Motor Test letters **A–D differ from motor numbers 1–4**.
- [ ] Stop testing; restore safety.

## 6) Flight Modes
- [ ] **Mandatory Hardware → Flight Modes:** assign `FLTMODE1…6` as required.
- [ ] Set `FLTMODE_CH = 6` if using RC6 for mode selection.
- [ ] Save/reload parameters; verify every reachable switch position.

## 7) Battery Monitor & Failsafe — 4S Example
- [ ] **Optional Hardware → Battery Monitor.**
- [ ] Select `INA2xx` / Holybro only if appropriate for the installed power module.
- [ ] Set actual capacity: `BATT_CAPACITY = 4000` mAh if using a 4000 mAh pack.
- [ ] Verify voltage against a meter; fully charged standard 4S LiPo ≈ **16.8 V**.
- [ ] **Low:** `BATT_LOW_VOLT = 14.4 V`; `BATT_FS_LOW_ACT = 2 (RTL)`.
- [ ] **Critical:** `BATT_CRT_VOLT = 14.0 V`; `BATT_FS_CRT_ACT = 1 (Land)`.
- [ ] Adjust thresholds for the pack and voltage sag; write parameters.

## 8) Initial Tuning
- [ ] Review **Initial Parameter Setup** for the actual propeller size and battery.
- [ ] Plan AutoTune after stable flight and completion of tuning preparation.

## 9) SiK Telemetry Radios — 433 MHz
- [ ] Recorded settings: `NETID = 40`; maximum frequency **434 MHz**—confirm suitability.
- [ ] Match required settings on both radios; save/write.
- [ ] Check frequency units: **434 MHz = 434000 kHz**.

## 10) Optional Servo Passthrough
- [ ] `SERVO8_FUNCTION = 1` passes **RC8 → output 8**.
- [ ] Assign the transmitter knob/switch to RC8; test movement.
- [ ] For another RC input, select its corresponding passthrough function.

## 11) Final Pre-Arm Checks — Every Flight
- [ ] Correct propellers installed and tightened **after all bench tests**.
- [ ] Battery charged and secured; frame and cables checked.
- [ ] Good GPS fix, healthy EKF/compass, correct Home position; satellite count alone is insufficient.
- [ ] No unresolved pre-arm warnings; arming checks enabled.
- [ ] Flight-mode switch works; intended takeoff mode selected.
- [ ] RTL altitude/action suit the field.
- [ ] Takeoff area clear; spotter briefed.

**Repeat motor position/direction checks after ESC or wiring changes.**
