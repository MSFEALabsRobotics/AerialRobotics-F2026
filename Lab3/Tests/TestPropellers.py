#TEST YOUR CRAZY FLY PROPERLLERS (NO need to restart drone after this) 
import time
from pathlib import Path

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie

URI = "radio://0/80/2M"
THRUST = 20000
DURATION = 1.5

cache = Path.home() / "crazyflie_cache"
cache.mkdir(exist_ok=True)

cflib.crtp.init_drivers()

with SyncCrazyflie(URI, cf=Crazyflie(rw_cache=str(cache))) as scf:
    cf = scf.cf

    try:
        cf.platform.send_arming_request(True)
        time.sleep(0.5)

        # Unlock startup thrust protection
        cf.commander.send_setpoint(0, 0, 0, 0)
        time.sleep(0.1)

        print("Testing motors...")
        end_time = time.monotonic() + DURATION

        while time.monotonic() < end_time:
            cf.commander.send_setpoint(0, 0, 0, THRUST)
            time.sleep(0.05)

    finally:
        # Keep sending zero thrust for 2 seconds
        for _ in range(40):
            cf.commander.send_setpoint(0, 0, 0, 0)
            time.sleep(0.05)

        # Then disarm before disconnecting
        cf.platform.send_arming_request(False)
        time.sleep(0.2)

        print("Motors stopped. Disconnected.")
