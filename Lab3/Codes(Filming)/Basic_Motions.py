# -*- coding: utf-8 -*-
#
#     ||          ____  _ __
#  +------+      / __ )(_) /_______________ _____  ___
#  | 0xBC |     / __  / / __/ ___/ ___/ __ `/_  / / _ \
#  +------+    / /_/ / / /_/ /__/ /  / /_/ / / /_/  __/
#   ||  ||    /_____/_/\__/\___/_/   \__,_/ /___/\___/
#
#  Copyright (C) 2018 Bitcraze AB
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA  02110-1301, USA.
"""
This script shows the basic use of the PositionHlCommander class.

Simple example that connects to the crazyflie at `URI` and runs a
sequence. This script requires some kind of location system.

The PositionHlCommander uses position setpoints.

Change the URI variable to your Crazyflie configuration.
"""
import time
import sys
sys.path.append('/home/bitcraze/Desktop/projects/crazyflie-lib-python/cflib/positioning/')

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger
from position_hl_commander import PositionHlCommander
from cflib.positioning.motion_commander import MotionCommander



# URI to the Crazyflie to connect to
uri = 'radio://0/30/2M'

def simple_sequence():
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        with PositionHlCommander(scf) as pc:

            pc.go_to(0,0,1)
            #pc.up(0.5)
            time.sleep(5)
            pc.forward(1.5,0.2)
            time.sleep(0.5)            
            pc.right(1.5)
            pc.back(0.5)
            pc.left(1.5)
            pc.back(1.0)
            pc.land()

def Motion_demo():
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        # We take off when the commander is created
        with MotionCommander(scf) as mc:
            time.sleep(1)
            # Go around obstacle , land and come back

            mc.up(0.5)
            time.sleep(1)
 
            # There is a set of functions that move a specific distance
            # We can move in all directions
            mc.forward(0.8)
            mc.back(0.8)
            time.sleep(1)

            mc.down(0.5)
            mc.up(0.5)
            time.sleep(1)

            # We can also set the velocity
            mc.right(0.5, velocity=0.8)
            time.sleep(1)
            mc.left(0.5, velocity=0.4)
            time.sleep(1)


            # Or turn
            mc.turn_left(90)
            mc.turn_right(90)
            time.sleep(1)

            # We can move along a line in 3D space
            mc.move_distance(-1, 0.0, 0.5, velocity=0.6)
            time.sleep(1)

            # We can move along a line in 3D space
            mc.move_distance(1, 0.0, -0.5, velocity=0.6)
            time.sleep(1)

            mc.circle_right(0.5, velocity=0.5, angle_degrees=360)



if __name__ == '__main__':
    cflib.crtp.init_drivers(enable_debug_driver=False)

    #simple_sequence()
    #slightly_more_complex_usage()
    Motion_demo()
