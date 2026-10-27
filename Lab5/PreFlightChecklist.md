# Mission Planner Setup and Pre-Flight Checklist
## Holybro Quad — ArduCopter

Reviewed against official ArduPilot documentation on 27 October 2026.

Use **Part A** during initial commissioning and after relevant hardware or configuration changes. Use **Part B** before every flight. Complete **Part C** during the first flight and after significant tuning changes.

Menu names and available parameters can differ with the installed Mission Planner and ArduCopter versions. Confirm parameter descriptions in the connected aircraft. Examples below are notes to verify, not a parameter file to upload.

Aircraft: __________  Flight controller: __________  ArduCopter version: __________
Mission Planner version: __________  Battery: __________  Propeller diameter: __________

## Part A — Initial setup / after relevant changes

### 1. Prepare and record

- [ ] Remove all propellers before calibration, motor testing, and failsafe bench tests.
- [ ] Check frame rigidity, motor mounts, wiring, connectors, and battery restraint.
- [ ] Connect by USB; record firmware version and save the current parameters before editing.
- [ ] Install the correct ArduCopter firmware for the flight controller only if needed; do not reflash before every flight.
- [ ] After changes, write parameters, reboot where required, and reload to verify persistence.

### 2. Frame and flight-controller orientation

- [ ] Under **SETUP → Frame Type**, select Quad / X if this matches the actual airframe.
- [ ] For the standard Quad X configuration: `FRAME_CLASS = 1` (Quad), `FRAME_TYPE = 1` (X).
- [ ] Confirm the flight controller's forward direction; configure `AHRS_ORIENTATION` if its mounting differs.
- [ ] With props removed, tilt the aircraft and check that Mission Planner's HUD follows its actual attitude.

Reference: [ArduCopter parameter definitions](https://ardupilot.org/copter/docs/parameters.html).

### 3. Accelerometer calibration

**SETUP → Mandatory Hardware → Accel Calibration**

- [ ] Set the correct board orientation first.
- [ ] Run the full six-position calibration, following the displayed order: level, left/right side, nose down, nose up, and upside down.
- [ ] Keep the aircraft still at every prompt.
- [ ] Confirm successful calibration.
- [ ] With the aircraft in its actual level flight attitude, use **Calibrate Level** if needed after mounting.
- [ ] Reboot if requested and recheck the HUD.

Calibrate Level refines the level reference; it does not replace the full six-position calibration.

Reference: [Accelerometer calibration](https://ardupilot.org/copter/docs/common-accelerometer-calibration.html).

### 4. Compass calibration

**SETUP → Mandatory Hardware → Compass**

- [ ] Identify the installed external and internal compasses; do not assume all compasses are in the GPS puck.
- [ ] Go outdoors, obtain a good 3D GPS fix, and move away from cars, steel, magnets, and electrical equipment.
- [ ] Use **Onboard Mag Calibration**, rather than the older Live/Offboard method.
- [ ] Rotate through all orientations as prompted; confirm success and reboot.
- [ ] Check that the displayed heading agrees with the aircraft's actual heading.

**Compass #3:** your old note to untick it is aircraft-specific. Disable a compass only after identifying a fault or persistent interference and confirming a healthy calibrated alternative. Its number alone is not a reason to disable it.

Reference: [Compass calibration](https://ardupilot.org/copter/docs/common-compass-calibration-in-mission-planner.html).

### 5. RC calibration and flight modes

**SETUP → Mandatory Hardware → Radio Calibration / Flight Modes**

- [ ] Calibrate all sticks, switches, and knobs through their intended ranges.
- [ ] Verify roll, pitch, yaw, and throttle mapping and direction.
- [ ] Check the calibrated minimum/maximum values for the actual throttle input; `RC3_MIN/MAX` applies if throttle is on RC3.
- [ ] Configure the modes reachable with the transmitter switch.
- [ ] If the mode switch is on RC6, use **`FLTMODE_CH = 6`**. Replace the old `MODE_CH` note.
- [ ] Assign `FLTMODE1 … FLTMODE6` as appropriate and verify each reachable switch position on the HUD. A three-position switch need not access all six slots.
- [ ] Provide familiar pilot modes and an accessible RTL selection. Record their switch positions.

Mode switch/input: __________  Pilot mode(s): __________  RTL position: __________

References: [Flight modes](https://ardupilot.org/copter/docs/flight-modes.html), [parameter definitions](https://ardupilot.org/copter/docs/parameters.html).

### 6. RC-loss failsafe — props removed

- [ ] Configure the receiver to report signal loss using its supported failsafe/no-signal method. Do not hold the last flight commands.
- [ ] `FS_THR_ENABLE = 1` selects RTL, with Land fallback if position is unusable; review `FS_OPTIONS` for exceptions.
- [ ] If using low-throttle failsafe, measure actual values. Example only: receiver loss output 960 µs, `FS_THR_VALUE = 975` µs, normal minimum 1000 µs.
- [ ] With the aircraft disarmed, switch off the transmitter and verify receiver-loss detection; restore the link.
- [ ] Follow the official props-off test procedure to verify armed handling. A landed aircraft, or Stabilize at minimum throttle, may **disarm rather than enter RTL**.
- [ ] Verify pilot recovery and disarm afterwards. Use SITL to check airborne RTL behavior; a bench test does not prove navigation.

Turning off the transmitter tests **RC loss**, not battery failsafe.

Reference: [Radio failsafe setup and testing](https://ardupilot.org/copter/docs/radio-failsafe.html).

### 7. ESC protocol, output mapping, and motor test — props removed

- [ ] Confirm `MOT_PWM_TYPE` matches the ESCs and that the selected outputs support the protocol.
- [ ] Calibrate throttle endpoints only if required by those ESCs. DShot and CAN ESCs do not need PWM throttle calibration.
- [ ] Verify each physical output against its assigned motor function. Standard mapping, only when wired accordingly:

| Output | Parameter | Function |
| --- | --- | --- |
| 1 | `SERVO1_FUNCTION = 33` | Motor 1 |
| 2 | `SERVO2_FUNCTION = 34` | Motor 2 |
| 3 | `SERVO3_FUNCTION = 35` | Motor 3 |
| 4 | `SERVO4_FUNCTION = 36` | Motor 4 |

- [ ] Open **SETUP → Optional Hardware → Motor Test**.
- [ ] If fitted, release the output safety using the hardware safety switch as required. This is distinct from arming.
- [ ] Test briefly at a low sufficient output; verify position and rotation against the **official diagram for the selected frame**.
- [ ] Distinguish Motor Test letters A/B/C/D from motor numbers 1/2/3/4; they are different ordering systems.
- [ ] Restore safety after testing.

Repeat motor checks after ESC, wiring, frame-type, or output-mapping changes.

References: [Motor diagrams and directions](https://ardupilot.org/copter/docs/connect-escs-and-motors.html), [output functions](https://ardupilot.org/copter/docs/common-rcoutput-mapping.html), [ESC calibration](https://ardupilot.org/copter/docs/esc-calibration.html).

### 8. Battery monitor and battery failsafe

**SETUP → Optional Hardware → Battery Monitor**, then the failsafe page or full parameter list.

- [ ] Identify the exact power-module model and select its documented monitor type. “Holybro” alone does not identify the electrical interface.
- [ ] Keep `INA2XX` only if appropriate for the installed digital module; confirm its model-specific configuration.
- [ ] Set `BATT_CAPACITY` to the actual pack capacity. Your recorded example was **4000 mAh**.
- [ ] Compare displayed voltage with a meter/cell checker; verify current sensing if using consumed-capacity estimates.
- [ ] Standard 4S LiPo is approximately **16.8 V fully charged** (4 × 4.2 V). The old **15.19 V** reading is not a fully charged reference.

Retained 4S examples — validate for the pack, load, voltage sag, and required return reserve:

| Parameter | Recorded example | Meaning |
| --- | --- | --- |
| `BATT_FS_LOW_ACT` | `2` | RTL, or Land if RTL is unavailable |
| `BATT_LOW_VOLT` | `14.4 V` | Low voltage |
| `BATT_FS_CRT_ACT` | `1` | Land |
| `BATT_CRT_VOLT` | `14.0 V` | Critical voltage |

- [ ] Review `BATT_LOW_TIMER` and `BATT_FS_VOLTSRC`; timing and raw/sag-corrected voltage affect triggering.
- [ ] Review remaining-capacity thresholds if used; they require dependable current measurement.
- [ ] Validate battery-failsafe logic separately in SITL or a controlled props-off procedure. Do not intentionally deeply discharge a flight pack to test it.

References: [Power-monitor setup](https://ardupilot.org/copter/docs/common-power-module-configuration-in-mission-planner.html), [battery failsafe](https://ardupilot.org/copter/docs/failsafe-battery.html), [battery voltage guidance](https://ardupilot.org/copter/docs/setting-up-for-tuning.html).

### 9. Initial parameters and tuning preparation

- [ ] Review **SETUP → Mandatory Hardware → Initial Parameter Setup** using the actual propeller diameter, cell count, and battery type.
- [ ] Review proposed settings before writing; recheck battery failsafe values afterwards.
- [ ] Confirm motor spin settings and the aircraft-specific initial filter/acceleration settings.
- [ ] Use the documented initial PID baseline or a verified configuration for this exact aircraft; do not assume every default fits every quad.
- [ ] Plan short initial flights and review logs for oscillation, vibration, and estimator problems.
- [ ] Schedule AutoTune only after completing the preparatory tuning steps and confirming controllable, stable flight.

References: [Setup for tuning](https://ardupilot.org/copter/docs/setting-up-for-tuning.html), [initial tuning flight](https://ardupilot.org/copter/docs/initial-tuning-flight.html).

### 10. Optional SiK telemetry radios

- [ ] Confirm both radios are the same compatible frequency-band variant.
- [ ] Your recorded `NETID = 40` is a chosen link identifier, not a required universal setting.
- [ ] Match required settings on air and ground radios: NETID, air rate, frequency limits, channel count, and other link settings listed in the radio documentation.
- [ ] The old **434 MHz maximum** is a recorded value requiring confirmation of the complete frequency range and permitted operating configuration.
- [ ] Check field units: raw `MIN_FREQ/MAX_FREQ` values use **kHz**; 434 MHz corresponds to 434000 kHz.
- [ ] Match each radio's serial speed to its attached port; save both ends and verify live telemetry with USB disconnected from the autopilot.

Reference: [SiK advanced configuration](https://ardupilot.org/copter/docs/common-3dr-radio-advanced-configuration-and-technical-information.html).

### 11. Optional servo passthrough

- [ ] Confirm the physical output, servo supply voltage, and appropriate servo-rail power.
- [ ] `SERVO8_FUNCTION = 1` passes **RC input 8 → output 8**.
- [ ] To pass a different RC input, select its explicit function. Example: **RC7 → output 8** uses `SERVO8_FUNCTION = 57` (RCPassThru7).
- [ ] Use an accessory input separate from the mode switch; test movement, safe travel, and RC-loss behavior with props removed.

Reference: [RC passthrough functions](https://ardupilot.org/copter/docs/common-rcoutput-mapping.html).

## Part B — Before EVERY flight

### Aircraft and flight area

- [ ] Frame, motors, landing gear, and wiring inspected; no damage or loose fasteners.
- [ ] Battery suitable for flight, adequately charged, securely attached, and connected correctly.
- [ ] Correct CW/CCW propellers installed in their verified positions, facing correctly, and tightened.
- [ ] Antennas, GPS/compass mount, and payload secure.
- [ ] Wind/weather and flight area suitable; takeoff, return, and landing areas clear.
- [ ] Pilot and spotter agree on the flight plan and abort procedure.

### Mission Planner and controls

- [ ] Power up on a stable surface; allow sensor initialization.
- [ ] Connected to the intended aircraft; telemetry updates normally.
- [ ] Battery voltage and remaining capacity plausible.
- [ ] HUD attitude and heading agree with the aircraft.
- [ ] No unresolved pre-arm failures; flight arming checks remain enabled.
- [ ] Healthy EKF and compass; for GPS navigation, obtain an acceptable 3D fix and position estimate.
- [ ] Confirm Home on the map at arming and the aircraft's actual location. Satellite count alone, including “8 sats,” does not prove navigation readiness.
- [ ] Transmitter battery and link healthy; correct model selected; stick/switch responses verified.
- [ ] Intended takeoff mode displayed; RTL switch position known.
- [ ] RTL altitude, return path, and landing behavior suit the field and obstacles.
- [ ] RC and battery failsafes retain the validated settings.
- [ ] If using AUTO/Guided, verify the mission/commands, limits, and pilot takeover before enabling them.
- [ ] Disconnect USB and clear people before arming; release safety only when ready.

Resolve warnings rather than bypassing arming checks.

References: [Pre-arm checks](https://ardupilot.org/copter/docs/common-prearm-safety-checks.html), [flight modes and position requirements](https://ardupilot.org/copter/docs/flight-modes.html).

## Part C — First flight / after significant tuning changes

- [ ] Use an experienced pilot familiar with Stabilize and the disarm procedure.
- [ ] Follow the documented initial tuning flight in an open area with low wind.
- [ ] Start in Stabilize; perform a brief lift-off and landing, then assess behavior.
- [ ] Land immediately if oscillation or abnormal behavior appears.
- [ ] Progress to AltHold and Loiter only after the preceding control behavior is verified.
- [ ] Review flight logs before longer flights, autonomous missions, or AutoTune.
- [ ] Save the verified parameter set with aircraft identity, firmware version, and date.

Reference: [Initial tuning flight](https://ardupilot.org/copter/docs/initial-tuning-flight.html).

## Aircraft-specific values still to confirm

| Item | Recorded note | Confirmed value |
| --- | --- | --- |
| Exact Holybro airframe / flight controller | Holybro Quad | __________ |
| ArduCopter / Mission Planner versions | Not recorded | __________ |
| Power-module model / monitor | INA2XX / Holybro | __________ |
| Battery chemistry / cell count / capacity | 4S / 4000 mAh example | __________ |
| Propeller size / ESC protocol | Not recorded | __________ |
| Flight-mode input | RC6 | __________ |
| RC-loss method / threshold | Approximately 960 µs loss output | __________ |
| Low / critical battery thresholds | 14.4 V / 14.0 V examples | __________ |
| Disabled compass identity / reason | Compass #3 | __________ |
| SiK NETID / complete band settings | 40 / maximum 434 MHz | __________ |
| RTL altitude / behavior | Not recorded | __________ |

