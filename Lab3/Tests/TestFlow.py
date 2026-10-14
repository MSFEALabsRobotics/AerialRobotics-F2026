import time
from pathlib import Path

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.syncLogger import SyncLogger

URI = "radio://0/80/2M"

cache = Path.home() / "crazyflie_cache"
cache.mkdir(exist_ok=True)

cflib.crtp.init_drivers()

log = LogConfig(name="Flow sensors", period_in_ms=100)
log.add_variable("range.zrange")
log.add_variable("motion.deltaX")
log.add_variable("motion.deltaY")

with SyncCrazyflie(
    URI, cf=Crazyflie(rw_cache=str(cache))
) as scf:
    print("Move the drone by hand. Motors remain OFF.")

    try:
        with SyncLogger(scf, log) as logger:
            start = time.monotonic()

            for timestamp, data, config in logger:
                height = data["range.zrange"]
                dx = data["motion.deltaX"]
                dy = data["motion.deltaY"]

                print(
                    f"Height: {height:6.0f} mm | "
                    f"Flow X: {dx:7.1f} | Flow Y: {dy:7.1f}"
                )

                if time.monotonic() - start >= 20:
                    break

    except KeyboardInterrupt:
        pass

print("Test finished.")
