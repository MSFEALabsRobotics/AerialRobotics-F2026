#!/usr/bin/env python3
"""apc_prop.py - rebuild an APC propeller as a 3D model from its geometry file.

    python apc_prop.py 8x8E-PERF.PE0        # one propeller, four files
    python apc_prop.py C:\\PE0-FILES_WEB     # a whole folder
    python apc_prop.py --check              # what this machine can do

Reads APC's propeller geometry files (the .PE0 files from APC's "Propeller
Geometry Data" archive, or the same content saved under any other name - the
parser reads the text, not the extension) and writes:

    APC_<name>.stl    binary STL, millimetres        (always)
    APC_<name>.obj    Wavefront OBJ, millimetres     (always)
    APC_<name>.step   STEP solid for CAD             (always; see below)
    APC_<name>.html   self-contained 3D viewer       (always)

Options
-------
    --formats=stl,step        write only these (of stl, obj, step, html)
    --check                   report the optional packages found, then stop
    --resume                  in folder mode, skip propellers already written
    --split                   in folder mode, give each propeller its own
                              folder, with a copy of its geometry file in it
    --hub-thickness=10mm      hub disc thickness, overriding the MAX-THICK the
                              file gives at r=0
    --bore=5mm                bore diameter, overriding the guess
                              Both accept mm, cm or in; a bare number means
                              inches, the unit the file itself uses.
    --step-ruled              loft the STEP as many small patches rather than
                              one spline surface per blade side; try this if a
                              CAD package struggles with the default
    --root-blend=2.0          radius, mm, for a fillet where the blade breaks
                              out of the hub's top face.  Currently a no-op on
                              this geometry: the root sections are buried
                              inside the hub, so there is no seam there to
                              round.  Left in for when that changes.
    --mesh=SEC,PTS            mesh density, spanwise and per surface (140,51)
    --step=SEC,PTS            the same for the STEP loft (56,41)

NOTHING outside the Python standard library is required.  Three optional
packages improve the result if they happen to be installed; the script reports
which it found and works without any of them:

    numpy + manifold3d   fuses the blades and hub into one watertight solid
                         instead of separate overlapping shells
                         ->  pip install numpy manifold3d
    cadquery             writes a true NURBS/B-rep STEP file instead of the
                         faceted one, which is what you want for real CAD work
                         ->  pip install cadquery

Geometry, and the assumptions behind it
---------------------------------------
Coordinates: X along the blade (radial), Y fore-aft in the rotation plane, Z
along thrust.  Rotation is right-handed about +Z, so the blade at +X moves
toward +Y and the leading edge is on the +Y side.  The LE (mould parting line)
sits at (y = SWEEP, z = RAKE) and the LE-TE line is inclined TE-down by TWIST.

Thickness is scaled by the file's THICKNESS RATIO and camber is carried
separately, because the two are independent: a station-wise thickness factor is
fitted to reproduce the file's CROSS-SECTION area, and a camber factor to put
the section centroid where CG(Y) and CG(Z) say.  ZHIGH is then left over as an
independent check and reported as you run; it lands within about 0.006 in
without being fitted.  Camber comes out near 5% of chord all along the span,
which is the shape of a real APC E section.

The hub is the row the table opens with, read literally: CHORD at r=0 is the
hub diameter, MAX-THICK is the disc thickness and ZHIGH is its top face.  That
is thinner than the hub thickness APC publish, because the published figure is
the overall depth of the part around the hub; adding the root flare recovers it
to within 0.01 in on the two propellers this was checked against.

Taken from the file: radius, station table, hub radius and thickness, blade
count, airfoil designations, density.  NOT in the file and assumed here: bore
diameter, trailing-edge thickness, and the moulded root fairing, which is why
the model comes out light against the file's TOTAL VOLUME - by 8% on the 8x8E
and 25% on the 7x9E, all of it inboard of HUBTRA.
"""
import base64
import math
import os
import platform
import re
import struct
import sys
import time

# --------------------------------------------------------------- assumptions
ROOT_BLEND = 0.0    # radius, mm, of the fillet where the blade meets the hub
STEP_RULED = False  # loft the STEP as ruled patches instead of one spline
HUB_T = None       # hub disc thickness in inches; None = MAX-THICK at r=0
BORE_D = None       # bore diameter, inches; None picks a standard size by hub
                    # size (APC uses 1/4, 3/8 or 1/2 in). This is the one thing
                    # here the file does not tell us.
TE_ABS = 0.008      # trailing-edge thickness, inches (~0.2 mm)
HUB_INSET = 0.55    # blades are lofted from this fraction of the hub radius,
                    # i.e. from well inside the hub, so the union is clean
HUB_EDGE = 0.22     # hub edge round, as a fraction of the hub half-height
N_PTS = 41          # points per airfoil surface when fitting
MESH_SEC = 140      # spanwise sections in the exported mesh
MESH_PTS = 51       # points per surface in the exported mesh
FORMATS = ('stl', 'obj', 'step', 'html')
STEP_SEC = 56       # spanwise sections in the faceted STEP fallback
STEP_PTS = 28       # points per surface in the faceted STEP fallback
STEP_NURBS_SEC = 56  # spanwise sections in the NURBS STEP loft
STEP_NURBS_PTS = 41  # points per surface in the NURBS STEP loft
VIEW_SEC = 90       # spanwise sections in the HTML viewer
VIEW_PTS = 33       # points per surface in the HTML viewer
HUB_FACETS = 64     # facets around the hub and bore
WELD_MM = 0.005     # weld vertices closer than this (mm) after fusing, which
                    # clears the slivers a boolean leaves behind
MM = 25.4

# Section coordinates, embedded so the script needs no data files and no
# network.  Selig order: TE -> upper -> LE -> lower -> TE, unit chord.
# APC quotes CLARK-Y on most propellers, E63 and APC12 on the electric
# ranges, and a NACA 16-series on a few.
AIRFOIL_DATA = {
    'clarky': (
        "1.00000,0.00060 0.99000,0.00297 0.98000,0.00533 0.97000,0.00769 0.96000,0.01002 "
        "0.94000,0.01462 0.92000,0.01912 0.90000,0.02350 0.88000,0.02779 0.86000,0.03197 "
        "0.84000,0.03605 0.82000,0.04002 0.80000,0.04388 0.78000,0.04763 0.76000,0.05126 "
        "0.74000,0.05477 0.72000,0.05816 0.70000,0.06143 0.68000,0.06458 0.66000,0.06760 "
        "0.64000,0.07048 0.62000,0.07321 0.60000,0.07576 0.58000,0.07815 0.56000,0.08035 "
        "0.54000,0.08237 0.52000,0.08421 0.50000,0.08588 0.48000,0.08736 0.46000,0.08864 "
        "0.44000,0.08972 0.42000,0.09057 0.40000,0.09117 0.38000,0.09152 0.36000,0.09163 "
        "0.34000,0.09151 0.32000,0.09119 0.30000,0.09068 0.28000,0.09000 0.26000,0.08908 "
        "0.24000,0.08783 0.22000,0.08614 0.20000,0.08392 0.18000,0.08107 0.16000,0.07757 "
        "0.14000,0.07344 0.12000,0.06862 0.10000,0.06300 0.08000,0.05643 0.06000,0.04876 "
        "0.05000,0.04428 0.04000,0.03913 0.03000,0.03302 0.02000,0.02537 0.01200,0.01786 "
        "0.00800,0.01374 0.00400,0.00892 0.00200,0.00580 0.00100,0.00373 0.00050,0.00234 "
        "0.00000,0.00000 0.00050,-0.00467 0.00100,-0.00594 0.00200,-0.00781 "
        "0.00400,-0.01051 0.00800,-0.01429 0.01200,-0.01697 0.02000,-0.02027 "
        "0.03000,-0.02261 0.04000,-0.02452 0.05000,-0.02605 0.06000,-0.02713 "
        "0.08000,-0.02846 0.10000,-0.02938 0.12000,-0.02996 0.14000,-0.03024 "
        "0.16000,-0.03025 0.18000,-0.03005 0.20000,-0.02967 0.22000,-0.02914 "
        "0.24000,-0.02852 0.26000,-0.02782 0.28000,-0.02707 0.30000,-0.02631 "
        "0.32000,-0.02556 0.34000,-0.02482 0.36000,-0.02409 0.38000,-0.02336 "
        "0.40000,-0.02263 0.42000,-0.02190 0.44000,-0.02117 0.46000,-0.02044 "
        "0.48000,-0.01970 0.50000,-0.01896 0.52000,-0.01823 0.54000,-0.01749 "
        "0.56000,-0.01676 0.58000,-0.01602 0.60000,-0.01529 0.62000,-0.01456 "
        "0.64000,-0.01382 0.66000,-0.01309 0.68000,-0.01235 0.70000,-0.01162 "
        "0.72000,-0.01088 0.74000,-0.01015 0.76000,-0.00941 0.78000,-0.00868 "
        "0.80000,-0.00794 0.82000,-0.00721 0.84000,-0.00648 0.86000,-0.00574 "
        "0.88000,-0.00501 0.90000,-0.00427 0.92000,-0.00354 0.94000,-0.00280 "
        "0.96000,-0.00207 0.97000,-0.00170 0.98000,-0.00133 0.99000,-0.00097 "
        "1.00000,-0.00060"),
    'e63': (
        "1.00000,0.00000 0.99719,0.00121 0.98938,0.00473 0.97751,0.00986 0.96173,0.01553 "
        "0.94164,0.02126 0.91717,0.02709 0.88861,0.03301 0.85624,0.03885 0.82039,0.04451 "
        "0.78141,0.04985 0.73968,0.05480 0.69562,0.05921 0.64967,0.06304 0.60229,0.06617 "
        "0.55394,0.06857 0.50509,0.07016 0.45624,0.07094 0.40786,0.07084 0.36043,0.06990 "
        "0.31441,0.06809 0.27026,0.06545 0.22840,0.06198 0.18920,0.05775 0.15304,0.05280 "
        "0.12023,0.04723 0.09103,0.04111 0.06568,0.03457 0.04435,0.02775 0.02714,0.02083 "
        "0.01416,0.01404 0.00536,0.00766 0.00076,0.00218 0.00055,-0.00141 0.00557,-0.00306 "
        "0.01651,-0.00330 0.03316,-0.00227 0.05550,-0.00004 0.08342,0.00315 0.11671,0.00708 "
        "0.15504,0.01151 0.19800,0.01620 0.24509,0.02093 0.29574,0.02546 0.34931,0.02962 "
        "0.40513,0.03319 0.46247,0.03605 0.52056,0.03803 0.57859,0.03907 0.63576,0.03907 "
        "0.69125,0.03806 0.74430,0.03604 0.79414,0.03310 0.84004,0.02930 0.88132,0.02482 "
        "0.91735,0.01979 0.94756,0.01439 0.97115,0.00887 0.98754,0.00410 0.99695,0.00102 "
        "1.00000,0.00000"),
    'e66': (
        "1.00000,0.00000 0.99670,0.00102 0.98743,0.00411 0.97320,0.00893 0.95441,0.01466 "
        "0.93098,0.02092 0.90305,0.02772 0.87110,0.03497 0.83556,0.04247 0.79689,0.04996 "
        "0.75550,0.05722 0.71179,0.06403 0.66620,0.07021 0.61916,0.07561 0.57113,0.08010 "
        "0.52254,0.08355 0.47386,0.08588 0.42551,0.08705 0.37796,0.08701 0.33164,0.08575 "
        "0.28696,0.08331 0.24435,0.07972 0.20418,0.07504 0.16684,0.06936 0.13265,0.06277 "
        "0.10192,0.05539 0.07490,0.04737 0.05182,0.03886 0.03283,0.03006 0.01807,0.02120 "
        "0.00759,0.01259 0.00150,0.00469 0.00021,-0.00159 0.00457,-0.00674 0.01464,-0.01162 "
        "0.02977,-0.01582 0.04987,-0.01912 0.07484,-0.02142 0.10454,-0.02272 "
        "0.13876,-0.02305 0.17724,-0.02247 0.21961,-0.02110 0.26547,-0.01905 "
        "0.31435,-0.01646 0.36572,-0.01346 0.41900,-0.01021 0.47359,-0.00684 "
        "0.52885,-0.00350 0.58412,-0.00033 0.63871,0.00255 0.69193,0.00500 0.74309,0.00692 "
        "0.79148,0.00823 0.83642,0.00885 0.87723,0.00876 0.91326,0.00797 0.94385,0.00648 "
        "0.96829,0.00443 0.98593,0.00227 0.99649,0.00062 1.00000,0.00000"),
    'naca16': (
        "1.00000,0.00090 0.99893,0.00111 0.99572,0.00176 0.99039,0.00283 0.98296,0.00431 "
        "0.97347,0.00618 0.96194,0.00839 0.94844,0.01089 0.93301,0.01359 0.91573,0.01644 "
        "0.89668,0.01938 0.87592,0.02237 0.85355,0.02534 0.82967,0.02825 0.80438,0.03103 "
        "0.77779,0.03364 0.75000,0.03603 0.72114,0.03817 0.69134,0.04003 0.66072,0.04159 "
        "0.62941,0.04286 0.59755,0.04382 0.56526,0.04449 0.53270,0.04488 0.50000,0.04500 "
        "0.46730,0.04488 0.43474,0.04453 0.40245,0.04396 0.37059,0.04317 0.33928,0.04218 "
        "0.30866,0.04100 0.27886,0.03965 0.25000,0.03814 0.22221,0.03648 0.19562,0.03467 "
        "0.17033,0.03274 0.14645,0.03070 0.12408,0.02855 0.10332,0.02632 0.08427,0.02401 "
        "0.06699,0.02158 0.05156,0.01908 0.03806,0.01649 0.02653,0.01375 0.01704,0.01098 "
        "0.00961,0.00814 0.00428,0.00534 0.00107,0.00267 0.00000,0.00000 0.00107,-0.00267 "
        "0.00428,-0.00534 0.00961,-0.00814 0.01704,-0.01098 0.02653,-0.01375 "
        "0.03806,-0.01649 0.05156,-0.01908 0.06699,-0.02158 0.08427,-0.02401 "
        "0.10332,-0.02632 0.12408,-0.02855 0.14645,-0.03070 0.17033,-0.03274 "
        "0.19562,-0.03467 0.22221,-0.03648 0.25000,-0.03814 0.27886,-0.03965 "
        "0.30866,-0.04100 0.33928,-0.04218 0.37059,-0.04317 0.40245,-0.04396 "
        "0.43474,-0.04453 0.46730,-0.04488 0.50000,-0.04500 0.53270,-0.04488 "
        "0.56526,-0.04449 0.59755,-0.04382 0.62941,-0.04286 0.66072,-0.04159 "
        "0.69134,-0.04003 0.72114,-0.03817 0.75000,-0.03603 0.77779,-0.03364 "
        "0.80438,-0.03103 0.82967,-0.02825 0.85355,-0.02534 0.87592,-0.02237 "
        "0.89668,-0.01938 0.91573,-0.01644 0.93301,-0.01359 0.94844,-0.01089 "
        "0.96194,-0.00839 0.97347,-0.00618 0.98296,-0.00431 0.99039,-0.00283 "
        "0.99572,-0.00176 0.99893,-0.00111 1.00000,-0.00090"),
    'n22': (
        "1.00000,0.00400 0.95000,0.01730 0.90000,0.03060 0.80000,0.05510 0.70000,0.07680 "
        "0.60000,0.09570 0.50000,0.11040 0.40000,0.12010 0.30000,0.12420 0.20000,0.12010 "
        "0.15000,0.11280 0.10000,0.10130 0.07500,0.09330 0.05000,0.08250 0.02500,0.06660 "
        "0.01250,0.05580 0.00000,0.03370 0.01250,0.01700 0.02500,0.01150 0.05000,0.00620 "
        "0.07500,0.00320 0.10000,0.00160 0.15000,0.00030 0.20000,0.00000 0.30000,0.00050 "
        "0.40000,0.00150 0.50000,0.00240 0.60000,0.00300 0.70000,0.00320 0.80000,0.00240 "
        "0.90000,0.00120 0.95000,0.00050 1.00000,0.00000"),
    'naca4412': (
        "1.00017,0.00125 1.00011,0.00127 0.99992,0.00132 0.99962,0.00140 0.99919,0.00152 "
        "0.99864,0.00167 0.99797,0.00186 0.99717,0.00208 0.99626,0.00233 0.99522,0.00262 "
        "0.99406,0.00294 0.99278,0.00329 0.99138,0.00367 0.98986,0.00409 0.98822,0.00453 "
        "0.98646,0.00501 0.98458,0.00552 0.98258,0.00606 0.98046,0.00663 0.97823,0.00724 "
        "0.97588,0.00787 0.97341,0.00852 0.97082,0.00921 0.96812,0.00993 0.96530,0.01067 "
        "0.96237,0.01144 0.95932,0.01223 0.95616,0.01306 0.95289,0.01390 0.94951,0.01477 "
        "0.94601,0.01567 0.94241,0.01658 0.93869,0.01752 0.93487,0.01849 0.93094,0.01947 "
        "0.92690,0.02047 0.92276,0.02149 0.91851,0.02254 0.91415,0.02360 0.90970,0.02467 "
        "0.90514,0.02577 0.90048,0.02688 0.89572,0.02800 0.89086,0.02914 0.88591,0.03029 "
        "0.88085,0.03146 0.87570,0.03264 0.87046,0.03383 0.86513,0.03503 0.85970,0.03624 "
        "0.85418,0.03745 0.84858,0.03868 0.84288,0.03991 0.83710,0.04115 0.83123,0.04240 "
        "0.82528,0.04365 0.81925,0.04490 0.81314,0.04616 0.80694,0.04742 0.80067,0.04868 "
        "0.79433,0.04994 0.78790,0.05120 0.78141,0.05246 0.77484,0.05372 0.76820,0.05498 "
        "0.76150,0.05623 0.75472,0.05748 0.74788,0.05873 0.74098,0.05996 0.73402,0.06120 "
        "0.72699,0.06242 0.71991,0.06364 0.71277,0.06484 0.70557,0.06604 0.69832,0.06723 "
        "0.69102,0.06841 0.68367,0.06957 0.67627,0.07072 0.66882,0.07186 0.66133,0.07299 "
        "0.65380,0.07410 0.64623,0.07519 0.63862,0.07627 0.63097,0.07733 0.62328,0.07837 "
        "0.61557,0.07940 0.60782,0.08041 0.60004,0.08139 0.59224,0.08236 0.58441,0.08331 "
        "0.57656,0.08423 0.56868,0.08513 0.56079,0.08601 0.55288,0.08687 0.54495,0.08770 "
        "0.53701,0.08850 0.52906,0.08929 0.52110,0.09004 0.51314,0.09077 0.50516,0.09147 "
        "0.49719,0.09215 0.48921,0.09280 0.48124,0.09342 0.47327,0.09401 0.46530,0.09457 "
        "0.45734,0.09510 0.44939,0.09560 0.44145,0.09607 0.43352,0.09651 0.42561,0.09692 "
        "0.41772,0.09730 0.40985,0.09764 0.40200,0.09796 0.39408,0.09823 0.38615,0.09846 "
        "0.37825,0.09863 0.37038,0.09876 0.36254,0.09883 0.35473,0.09886 0.34697,0.09883 "
        "0.33923,0.09876 0.33155,0.09863 0.32390,0.09846 0.31630,0.09824 0.30874,0.09797 "
        "0.30124,0.09765 0.29378,0.09728 0.28638,0.09686 0.27904,0.09640 0.27175,0.09589 "
        "0.26452,0.09533 0.25736,0.09473 0.25025,0.09408 0.24322,0.09339 0.23625,0.09265 "
        "0.22935,0.09187 0.22253,0.09105 0.21578,0.09018 0.20910,0.08928 0.20250,0.08834 "
        "0.19598,0.08735 0.18955,0.08633 0.18319,0.08528 0.17692,0.08418 0.17074,0.08305 "
        "0.16465,0.08189 0.15864,0.08069 0.15273,0.07946 0.14691,0.07821 0.14119,0.07692 "
        "0.13556,0.07560 0.13003,0.07425 0.12460,0.07288 0.11927,0.07149 0.11404,0.07007 "
        "0.10892,0.06862 0.10390,0.06716 0.09899,0.06567 0.09418,0.06417 0.08949,0.06265 "
        "0.08490,0.06111 0.08042,0.05956 0.07606,0.05799 0.07181,0.05641 0.06768,0.05482 "
        "0.06366,0.05322 0.05975,0.05161 0.05596,0.04999 0.05229,0.04836 0.04874,0.04673 "
        "0.04531,0.04509 0.04200,0.04346 0.03881,0.04181 0.03574,0.04017 0.03280,0.03853 "
        "0.02997,0.03689 0.02727,0.03525 0.02470,0.03361 0.02225,0.03198 0.01992,0.03036 "
        "0.01772,0.02873 0.01564,0.02712 0.01369,0.02551 0.01187,0.02392 0.01017,0.02233 "
        "0.00860,0.02075 0.00716,0.01918 0.00585,0.01762 0.00466,0.01608 0.00360,0.01455 "
        "0.00266,0.01303 0.00186,0.01152 0.00118,0.01003 0.00063,0.00855 0.00021,0.00709 "
        "-0.00009,0.00564 -0.00026,0.00421 -0.00030,0.00279 -0.00021,0.00139 "
        "0.00000,0.00000 0.00034,-0.00136 0.00080,-0.00269 0.00138,-0.00398 "
        "0.00208,-0.00524 0.00291,-0.00647 0.00385,-0.00766 0.00492,-0.00881 "
        "0.00611,-0.00994 0.00741,-0.01102 0.00884,-0.01208 0.01038,-0.01310 "
        "0.01205,-0.01409 0.01383,-0.01504 0.01572,-0.01596 0.01773,-0.01684 "
        "0.01986,-0.01770 0.02210,-0.01852 0.02446,-0.01930 0.02693,-0.02005 "
        "0.02951,-0.02077 0.03221,-0.02146 0.03501,-0.02212 0.03793,-0.02274 "
        "0.04095,-0.02333 0.04408,-0.02389 0.04732,-0.02442 0.05066,-0.02492 "
        "0.05412,-0.02539 0.05767,-0.02582 0.06133,-0.02623 0.06509,-0.02661 "
        "0.06895,-0.02696 0.07291,-0.02727 0.07697,-0.02756 0.08113,-0.02783 "
        "0.08539,-0.02806 0.08974,-0.02827 0.09418,-0.02845 0.09872,-0.02860 "
        "0.10336,-0.02873 0.10808,-0.02883 0.11289,-0.02891 0.11780,-0.02896 "
        "0.12279,-0.02899 0.12786,-0.02900 0.13303,-0.02898 0.13827,-0.02895 "
        "0.14360,-0.02889 0.14901,-0.02881 0.15450,-0.02871 0.16007,-0.02859 "
        "0.16572,-0.02845 0.17145,-0.02829 0.17725,-0.02812 0.18312,-0.02793 "
        "0.18907,-0.02773 0.19508,-0.02751 0.20117,-0.02727 0.20733,-0.02702 "
        "0.21355,-0.02676 0.21984,-0.02649 0.22619,-0.02621 0.23261,-0.02591 "
        "0.23909,-0.02561 0.24563,-0.02530 0.25223,-0.02498 0.25889,-0.02465 "
        "0.26560,-0.02432 0.27237,-0.02398 0.27919,-0.02364 0.28606,-0.02329 "
        "0.29299,-0.02294 0.29996,-0.02259 0.30698,-0.02224 0.31405,-0.02189 "
        "0.32116,-0.02154 0.32832,-0.02119 0.33552,-0.02084 0.34275,-0.02050 "
        "0.35003,-0.02016 0.35734,-0.01982 0.36469,-0.01950 0.37207,-0.01917 "
        "0.37949,-0.01886 0.38694,-0.01855 0.39441,-0.01825 0.40195,-0.01796 "
        "0.40960,-0.01766 0.41727,-0.01737 0.42497,-0.01706 0.43269,-0.01676 "
        "0.44043,-0.01645 0.44818,-0.01613 0.45594,-0.01581 0.46372,-0.01549 "
        "0.47151,-0.01517 0.47931,-0.01485 0.48711,-0.01453 0.49492,-0.01420 "
        "0.50273,-0.01388 0.51054,-0.01355 0.51835,-0.01323 0.52616,-0.01291 "
        "0.53397,-0.01258 0.54177,-0.01226 0.54956,-0.01195 0.55734,-0.01163 "
        "0.56510,-0.01132 0.57286,-0.01101 0.58060,-0.01071 0.58832,-0.01041 "
        "0.59602,-0.01011 0.60369,-0.00981 0.61135,-0.00953 0.61898,-0.00924 "
        "0.62658,-0.00896 0.63415,-0.00869 0.64170,-0.00842 0.64920,-0.00815 "
        "0.65668,-0.00789 0.66412,-0.00764 0.67151,-0.00739 0.67887,-0.00715 "
        "0.68619,-0.00692 0.69346,-0.00669 0.70069,-0.00646 0.70786,-0.00624 "
        "0.71499,-0.00603 0.72207,-0.00582 0.72909,-0.00562 0.73606,-0.00543 "
        "0.74297,-0.00524 0.74983,-0.00506 0.75662,-0.00488 0.76335,-0.00471 "
        "0.77002,-0.00455 0.77662,-0.00439 0.78315,-0.00423 0.78962,-0.00409 "
        "0.79602,-0.00394 0.80234,-0.00381 0.80859,-0.00367 0.81476,-0.00355 "
        "0.82086,-0.00342 0.82688,-0.00331 0.83281,-0.00320 0.83867,-0.00309 "
        "0.84444,-0.00298 0.85013,-0.00289 0.85573,-0.00279 0.86124,-0.00270 "
        "0.86667,-0.00262 0.87200,-0.00254 0.87724,-0.00246 0.88239,-0.00238 "
        "0.88744,-0.00231 0.89240,-0.00225 0.89726,-0.00218 0.90202,-0.00212 "
        "0.90668,-0.00206 0.91124,-0.00201 0.91569,-0.00196 0.92005,-0.00191 "
        "0.92429,-0.00186 0.92843,-0.00182 0.93247,-0.00178 0.93639,-0.00174 "
        "0.94021,-0.00170 0.94392,-0.00166 0.94751,-0.00163 0.95099,-0.00160 "
        "0.95436,-0.00157 0.95761,-0.00154 0.96075,-0.00152 0.96378,-0.00149 "
        "0.96668,-0.00147 0.96947,-0.00145 0.97214,-0.00143 0.97469,-0.00141 "
        "0.97712,-0.00139 0.97943,-0.00138 0.98162,-0.00136 0.98369,-0.00135 "
        "0.98563,-0.00134 0.98745,-0.00132 0.98915,-0.00131 0.99073,-0.00130 "
        "0.99218,-0.00129 0.99350,-0.00129 0.99470,-0.00128 0.99578,-0.00127 "
        "0.99673,-0.00127 0.99755,-0.00126 0.99825,-0.00126 0.99882,-0.00125 "
        "0.99926,-0.00125 0.99958,-0.00125 0.99977,-0.00125 0.99983,-0.00125"),
}

def bore_for(hub_r):
    """APC fits one of a few standard bores; pick by hub size."""
    for limit, d in ((0.45, 0.25), (0.70, 0.375)):
        if hub_r <= limit:
            return d
    return 0.5


# APC's designations mapped onto those sections.  APC12 is NACA 4412; the
# APC16xxxR names are NACA 16-series, whose thickness is rescaled per station
# from the file anyway, so one 16-series shape serves them all.
AIRFOIL_ALIASES = {
    'CLARK-Y': 'clarky', 'CLARKY': 'clarky', 'CLARK Y': 'clarky',
    'APC12': 'naca4412', 'APC-12': 'naca4412',
    'E63': 'e63', 'E66': 'e66', 'N-22A': 'n22', 'N22A': 'n22',
    'APC16009R': 'naca16', 'APC16006R': 'naca16', 'APC16': 'naca16',
}


# ============================================================ optional imports
def probe():
    """What is available on this machine.  Never raises."""
    have = {}
    for mod in ('numpy', 'manifold3d', 'cadquery'):
        try:
            __import__(mod)
            have[mod] = True
        except BaseException:
            have[mod] = False
    return have


def report(have, verbose=True):
    if verbose:
        print('python %s on %s (%s)' % (platform.python_version(),
                                        platform.system(), platform.machine()))
    fuse = have['numpy'] and have['manifold3d']
    print('  solid fusion : %s' % ('yes (numpy + manifold3d)' if fuse else
                                   'no  -> blades and hub written as separate '
                                   'shells; pip install numpy manifold3d'))
    print('  STEP quality : %s' % ('NURBS B-rep (cadquery)' if have['cadquery'] else
                                   'faceted  -> pip install cadquery for a '
                                   'smooth CAD solid'))
    return have


# ================================================================ file parsing
def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def load_stations(txt, path='<file>'):
    """The AIRFOIL SUMMARY DATA table, read by column name rather than by
    counting columns.

    Three layouts appear in APC's archive.  The usual one has fourteen columns
    including RAKE(Z).  The folding and folding-multirotor files have thirteen
    and no RAKE at all, which for a blade with a flat parting line means zero.
    At least one file, the 15x12E, has fourteen columns that are NOT the usual
    fourteen: no RAKE, and a trailing PITCH(REAL).  Counting columns reads that
    file as the usual layout, shifted, and every value from SWEEP outwards
    lands in the wrong place: its thickness ratio is read as a rake, its twist
    as a thickness ratio, and the model comes out several times too heavy
    without anything looking wrong.  So the header is parsed instead.

    Only the text between that heading and the RADIUS: line is scanned, so no
    other block can be misread as data.
    """
    body = txt
    i = txt.find('AIRFOIL SUMMARY DATA')
    if i >= 0:
        body = txt[i:]
        j = body.find('RADIUS:')
        if j > 0:
            body = body[:j]
    lines = body.splitlines()

    labels = None
    for k, line in enumerate(lines):
        if 'STATION' in line and 'CHORD' in line:
            head = line.split()
            unit = lines[k + 1].split() if k + 1 < len(lines) else []
            # The name of a column can be split across the two heading lines:
            # "THICKNESS" over "RATIO", and PITCH appears three or four times
            # distinguished only by its unit, "(QUOTED)", "(LE-TE)" and so on.
            labels = []
            for n, name in enumerate(head):
                tail = unit[n] if n < len(unit) else ''
                if tail.upper() == 'RATIO' or not tail.startswith('('):
                    name = (name + ' ' + tail).strip()
                elif name.upper() == 'PITCH':
                    name = name + tail
                labels.append(name.upper().replace('(Y)', '').replace('(Z)', ''))
            break

    WANT = {'r': 'STATION', 'chord': 'CHORD', 'pitch_q': 'PITCH(QUOTED)',
            'pitch_lete': 'PITCH(LE-TE)', 'pitch_pr': 'PITCH(PRATHER)',
            'sweep': 'SWEEP', 'rake': 'RAKE', 'tr': 'THICKNESS RATIO',
            'twist': 'TWIST', 'tmax': 'MAX-THICK', 'area': 'CROSS-SECTION',
            'zhigh': 'ZHIGH', 'cgy': 'CGY', 'cgz': 'CGZ'}
    OPTIONAL = {'rake'}

    rows = []
    if labels:
        for line in lines:
            p = line.split()
            if len(p) != len(labels):
                continue
            try:
                rows.append([float(v) for v in p])
            except ValueError:
                pass
    if len(rows) < 5:
        raise SystemExit(
            'No usable station table in %s (found %d rows, expected dozens).\n'
            'This should be an APC geometry file - the .PE0 files in APC\'s '
            '"Propeller Geometry Data" archive.\nA performance file will not '
            'work: it has no blade geometry in it.' % (path, len(rows)))

    index = {}
    for key, name in WANT.items():
        if name in labels:
            index[key] = labels.index(name)
        elif key not in OPTIONAL:
            raise SystemExit(
                'The station table in %s has no %s column.\nIts heading reads: '
                '%s\nThat is a layout this script does not know; the columns it '
                'needs are %s.'
                % (path, name, ' '.join(labels), ', '.join(sorted(WANT.values()))))
    out = {}
    for key in WANT:
        n = index.get(key)
        out[key] = [0.0] * len(rows) if n is None else [row[n] for row in rows]
    return out


def load_header(txt, path):
    def num(pat, default=float('nan')):
        m = re.search(pat + r'\s*=\s*([-\d.Ee+]+)', txt)
        return float(m.group(1)) if m else default

    def field(key, default=None):
        m = re.search(key + r':\s*([-\d.]+)', txt)
        return float(m.group(1)) if m else default

    lines = txt.splitlines()
    first = lines[0] if lines else ''
    m = re.search(r'\(([^)]+)\)', first)
    foils = [(float(a), b.strip().upper()) for _, a, b in
             re.findall(r'AIRFOIL(\d):\s*([\d.]+)\s*,\s*([A-Za-z0-9\- ]+?)\s*\(', txt)]
    return dict(
        name=first.split('(')[0].strip() or os.path.basename(path),
        source=', '.join(x for x in [m.group(1) if m else os.path.basename(path),
                                     lines[1].strip() if len(lines) > 1 else ''] if x),
        hub_r=field('HUBRAD'), hubtra=field('HUBTRA'), blades=int(field('BLADES', 2) or 2),
        file_vol=num(r'TOTAL VOLUME \(IN\*\*3\)'),
        file_mass_g=num(r'TOTAL WEIGHT \(Kg\)') * 1000.0,
        sg=num(r'DENSITY \(SPECIFIC GRAVITY, INPUT FILE\)', 1.70),
        airfoils=foils or [(0.0, 'CLARK-Y')])


# =================================================================== airfoils
def parse_coords(text):
    out = []
    for tok in text.split():
        a, b = tok.split(',')
        out.append((float(a), float(b)))
    return out


def naca4(code, n=200):
    """Coordinates for a NACA 4-digit section, so APC12 (= NACA 4412) needs no
    data file either."""
    m, p, t = int(code[0]) / 100.0, int(code[1]) / 10.0, int(code[2:]) / 100.0
    up, lo = [], []
    for i in range(n + 1):
        x = 0.5 * (1 - math.cos(math.pi * i / n))
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.1260 * x - 0.3516 * x * x
                      + 0.2843 * x ** 3 - 0.1015 * x ** 4)
        if p > 0 and x < p:
            yc = m / p ** 2 * (2 * p * x - x * x)
            dy = 2 * m / p ** 2 * (p - x)
        elif p > 0:
            yc = m / (1 - p) ** 2 * ((1 - 2 * p) + 2 * p * x - x * x)
            dy = 2 * m / (1 - p) ** 2 * (p - x)
        else:
            yc, dy = 0.0, 0.0
        th = math.atan(dy)
        up.append((x - yt * math.sin(th), yc + yt * math.cos(th)))
        lo.append((x + yt * math.sin(th), yc - yt * math.cos(th)))
    return up[::-1] + lo[1:]


def resolve_airfoil(name, warn=None):
    """Coordinates for an APC airfoil designation.  In order of preference: a
    Selig-format <name>.dat beside the script or in the working directory, one
    of the embedded sections, an analytic NACA 4-digit, and failing all that
    Clark-Y with a note.  Falling back is reasonable because every section is
    rescaled per station to the file's own thickness and area, so an unknown
    designation costs shape fidelity, not gross accuracy."""
    key = name.strip().upper()
    alias = AIRFOIL_ALIASES.get(key, key.lower().replace('-', ''))
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (alias + '.dat', key.lower() + '.dat',
                 key.lower().replace('-', '') + '.dat'):
        for p in (cand, os.path.join(here, cand)):
            if os.path.exists(p):
                pts = []
                for line in open(p):
                    f = line.split()
                    if len(f) == 2:
                        try:
                            pts.append((float(f[0]), float(f[1])))
                        except ValueError:
                            pass
                if len(pts) > 10:
                    return pts
    if alias in AIRFOIL_DATA:
        return parse_coords(AIRFOIL_DATA[alias])
    m = re.match(r'^(?:NACA)?(\d{4})$', alias.upper())
    if m:
        return naca4(m.group(1))
    if warn is not None:
        warn.append(name)
    return parse_coords(AIRFOIL_DATA['clarky'])


def camber_thickness(af, n):
    """Split a resampled airfoil into camber and thickness distributions.
    Thickness is non-negative by construction, which is what keeps every fitted
    section simple."""
    up = af[:n][::-1]                      # LE -> TE, upper
    lo = af[n - 1:]                        # LE -> TE, lower
    cam = [0.5 * (u[1] + l[1]) for u, l in zip(up, lo)]
    thk = [max(0.0, u[1] - l[1]) for u, l in zip(up, lo)]
    return cam, thk


def resample(coords, n):
    """Cosine-spaced, TE(upper) -> LE -> TE(lower), normalised to unit maximum
    thickness so the file's THICKNESS RATIO scales it directly."""
    i_le = min(range(len(coords)), key=lambda i: coords[i][0])
    up = coords[:i_le + 1][::-1]          # LE -> TE
    lo = coords[i_le:]                    # LE -> TE
    xs = [0.5 * (1 - math.cos(math.pi * i / (n - 1))) for i in range(n)]
    yu = [interp(x, [p[0] for p in up], [p[1] for p in up]) for x in xs]
    yl = [interp(x, [p[0] for p in lo], [p[1] for p in lo]) for x in xs]
    t = max(a - b for a, b in zip(yu, yl))
    yu = [v / t for v in yu]
    yl = [v / t for v in yl]
    pts = [(xs[i], yu[i]) for i in range(n - 1, -1, -1)]      # TE -> LE, upper
    pts += [(xs[i], yl[i]) for i in range(1, n)]              # LE -> TE, lower
    return pts


def interp(x, xs, ys):
    """Linear interpolation on an ascending grid, clamped at both ends."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xs[mid] <= x:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    f = 0.0 if span == 0 else (x - xs[lo]) / span
    return ys[lo] + f * (ys[hi] - ys[lo])


# ===================================================== numerics (stdlib only)
def bisect(f, lo, hi, floor, ceil, tol=1e-10, it=200):
    """Root of f, widening the bracket within [floor, ceil].  Returns
    (value, exact) - exact is False if no sign change could be bracketed and
    the closest approach was used instead."""
    flo, fhi = f(lo), f(hi)
    for _ in range(8):
        if flo * fhi <= 0:
            break
        span = hi - lo
        lo, hi = max(floor, lo - 0.5 * span), min(ceil, hi + 0.5 * span)
        flo, fhi = f(lo), f(hi)
        if lo <= floor and hi >= ceil:
            break
    if flo * fhi > 0:
        return golden(lambda v: abs(f(v)), lo, hi), False
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if hi - lo < tol:
            break
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi), True


def golden(f, lo, hi, it=90):
    g = (math.sqrt(5) - 1) / 2
    c, d = hi - g * (hi - lo), lo + g * (hi - lo)
    fc, fd = f(c), f(d)
    for _ in range(it):
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - g * (hi - lo)
            fc = f(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + g * (hi - lo)
            fd = f(d)
    return 0.5 * (lo + hi)


def smooth(vals, win=7):
    """Savitzky-Golay-style smoothing: a local quadratic least-squares fit,
    solved directly.  Keeps the ends where a centred window will not fit."""
    n = len(vals)
    half = min(win, n if n % 2 else n - 1) // 2
    if half < 2:
        return list(vals)
    out = []
    for i in range(n):
        a = max(0, min(i - half, n - 2 * half - 1))
        b = a + 2 * half + 1
        xs = [j - i for j in range(a, b)]
        ys = vals[a:b]
        out.append(quadfit(xs, ys))
    return out


def quadfit(xs, ys):
    """Value at x = 0 of the least-squares quadratic through (xs, ys)."""
    s = [sum(x ** k for x in xs) for k in range(5)]
    t = [sum(y * x ** k for x, y in zip(xs, ys)) for k in range(3)]
    A = [[s[0], s[1], s[2], t[0]],
         [s[1], s[2], s[3], t[1]],
         [s[2], s[3], s[4], t[2]]]
    for c in range(3):                       # Gaussian elimination, 3x3
        p = max(range(c, 3), key=lambda r: abs(A[r][c]))
        if abs(A[p][c]) < 1e-14:
            return sum(ys) / len(ys)
        A[c], A[p] = A[p], A[c]
        for r in range(3):
            if r != c:
                f = A[r][c] / A[c][c]
                for k in range(c, 4):
                    A[r][k] -= f * A[c][k]
    return A[0][3] / A[0][0]


def poly_area_centroid(pts):
    """Area and centroid of a closed 2D polygon (shoelace)."""
    a = cy = cz = 0.0
    n = len(pts)
    for i in range(n):
        y0, z0 = pts[i]
        y1, z1 = pts[(i + 1) % n]
        cr = y0 * z1 - y1 * z0
        a += cr
        cy += (y0 + y1) * cr
        cz += (z0 + z1) * cr
    a *= 0.5
    if abs(a) < 1e-15:
        return 0.0, 0.0, 0.0
    return abs(a), cy / (6 * a), cz / (6 * a)


# ============================================================ blade definition
class Blade(object):
    """Section geometry for one blade, fitted to the file's own numbers."""

    def __init__(self, st, hdr, quiet=False):
        self.st = st
        self.hdr = hdr
        self.r_tip = st['r'][-1]
        # A folding propeller has no hub: its blades pin into one sold
        # separately, so the file carries no HUBRAD and its table starts where
        # the blade starts, at HUBTRA.  There is nothing to build a disc from
        # and nothing inboard to loft into, so the model is one blade, capped
        # at its root, and no bore.
        self.hubless = not hdr['hub_r']
        self.hub_r = hdr['hub_r'] or st['r'][0]
        # HUBTRA is where APC's root fairing ends and the blade proper begins.
        # Inboard of it the table's area and ZHIGH describe hub material, not
        # an aerofoil, so the section fit is only trusted from there out.
        self.hubtra = hdr['hubtra'] or 2.5 * self.hub_r
        self.bore = BORE_D if BORE_D is not None else bore_for(self.hub_r)
        # The hub is a round cylinder of the file's HUBRAD.  Its height is not
        # in the file; it is taken from the height of the blade root where it
        # enters the hub, which the hub must enclose.  The rows the table
        # carries between HUBRAD and HUBTRA are APC's root fairing, and lofting
        # through them is what blends the blade into the hub.

        foils = hdr['airfoils']
        self.r_a, self.name_a = foils[0]
        self.r_b, self.name_b = foils[-1]
        unknown = []
        self.cam_a, self.thk_a = camber_thickness(
            resample(resolve_airfoil(self.name_a, unknown), N_PTS), N_PTS)
        if self.name_b == self.name_a:
            self.cam_b, self.thk_b = self.cam_a, self.thk_a
        else:
            self.cam_b, self.thk_b = camber_thickness(
                resample(resolve_airfoil(self.name_b, unknown), N_PTS), N_PTS)
        self.unknown_airfoils = unknown
        self.xs = [0.5 * (1 - math.cos(math.pi * i / (N_PTS - 1))) for i in range(N_PTS)]
        self.bump = [4 * x * (1 - x) for x in self.xs]
        # Camber is normalised to unit height and carried separately from the
        # thickness.  resample() divides the aerofoil by its own maximum
        # thickness, so its camber line comes out scaled by 1/t as well; left
        # that way, multiplying the whole profile by THICKNESS RATIO ties the
        # camber to the thickness and gives an 18%-cambered root against a
        # 5%-cambered tip.  The file's CG(Y)/CG(Z) columns say the real
        # sections hold about 5% camber all the way along, so camber gets its
        # own per-station scale fitted to those columns.
        self.cam_a = self._unit(self.cam_a)
        self.cam_b = self.cam_a if self.name_b == self.name_a else self._unit(self.cam_b)
        self.i_le = N_PTS - 1
        self.clamped = []
        self._ke = None
        self._top = None
        self.r_ex, self.ke = [], []
        if not quiet:
            if self.name_b == self.name_a:
                print('  airfoil      : %s throughout' % self.name_a)
            else:
                print('  airfoil      : %s inboard of r=%.2f, morphing to %s by r=%.2f'
                      % (self.name_a, self.r_a, self.name_b, self.r_b))
            if unknown:
                print('  note         : no coordinates for %s; using Clark-Y '
                      'rescaled to this file\'s thickness and area.'
                      % ', '.join(sorted(set(unknown))))
        self._fit(quiet)
        self._hub_and_line()

    def _bury(self, r, up, lo):
        """Shrink a section that lies inside the hub until it fits there.

        The loft has to start inside the hub, or the blade would end on a flat
        cut at the hub's surface.  What it starts on is not a real section: the
        table's rows there are the hub disc, and carrying the aerofoil in on
        its own chord and rake instead leaves it poking out through the hub's
        rim and faces.  So sections inside HUBRAD are recentred on the hub and
        scaled to sit inside it, with a little clearance.  Every one of them is
        swallowed by the hub, so this changes what the model looks like nowhere
        and only keeps the boolean clean."""
        h, top = self.hub_h, self.hub_top
        if h <= 0:
            return up, lo
        pts = up + lo
        ys = [q[1] for q in pts]
        zs = [q[2] for q in pts]
        ymid = 0.5 * (min(ys) + max(ys))
        zmid = 0.5 * (min(zs) + max(zs))
        wide = 0.90 * math.sqrt(max(0.0, self.hub_r ** 2 - r * r))
        sy = min(1.0, 2 * wide / max(max(ys) - min(ys), 1e-9))
        sz = min(1.0, 0.85 * h / max(max(zs) - min(zs), 1e-9))
        zc = top - 0.5 * h
        # Eased in from the hub surface inwards, so the loft has no step in it
        # to trip over where the shrinking starts.
        t = min(1.0, max(0.0, (self.hub_r - r)
                         / max(1e-9, (1 - HUB_INSET) * self.hub_r)))
        w = t * t * (3 - 2 * t)

        def f(q):
            y = (q[1] - ymid) * sy
            z = (q[2] - zmid) * sz + zc
            return (q[0], q[1] + w * (y - q[1]), q[2] + w * (z - q[2]))

        return [f(q) for q in up], [f(q) for q in lo]

    def _fair(self, r, lo):
        """The root carries no added material: the blade runs into the hub as a
        thinning aerofoil, which is what the part does.

        An earlier version floored the underside of the root onto the plane of
        the hub face, to pick up the CROSS-SECTION the table quotes inboard of
        HUBTRA.  It matched that column to a few per cent, but a floor is a
        plane, and it showed as a flat panel under the root with a straight
        edge across the blend.  The column it was chasing is describing the
        root swelling into the hub, which is a fillet; until that is modelled
        as one, the honest shape is the aerofoil, and the volume it gives up is
        noted in the build summary."""
        return lo

    def rake_at(self, r):
        """Height of the leading edge at radius r.

        The table's RAKE column turns down hard as it nears the axis: it is
        following the mould parting line onto the flat face of the hub, so it
        is forced to the centre plane at r=0, which drags the top of the root
        down with it.  On the part the upper line runs straight off the top
        edge of the hub.  Inboard of HUBTRA the section is therefore lifted so
        that its highest point follows a straight line from where the blade
        proper starts to the top face of the hub, and the lift is zero at
        HUBTRA so nothing kinks where the two meet."""
        rake = self.at('rake', r)
        top = getattr(self, '_top', None)
        if top is None or r >= self.hubtra:
            return rake
        r0, z0, z1 = self.hub_r, self.hub_top, top
        f = min(1.0, max(0.0, (self.hubtra - r) / max(1e-9, self.hubtra - r0)))
        want = z1 + (z0 - z1) * f              # straight in r
        self._top = None                        # avoid recursion on this probe
        try:
            have = max(q[2] for q in self.section(r, *self.factors(r)))
        finally:
            self._top = top
        return rake + (want - have)

    def _hub_and_line(self):
        """Hub thickness, and the height of the blade where it leaves HUBTRA.

        The hub is the row the table opens with.  At r=0 the section is the hub
        disc seen edge on: CHORD there is the hub diameter, MAX-THICK is how
        thick the disc is, and ZHIGH is where its top face sits.  So the hub is
        that disc, and nothing about it is assumed.

        It is thinner than the hub thickness APC publish, because that figure
        is the overall depth of the part around the hub, not the disc: adding
        the root flare a little further out recovers it.  On the 8x8E the disc
        runs from +0.100 to -0.247 in and the root reaches +0.164, giving 0.411
        against a published 0.40; on the 7x9E, +0.110 to -0.094 with the root
        at +0.211 gives 0.376 against 0.38."""
        self._top = self.hub_h = 0.0
        self.hub_top = 0.0
        if self.hubless:
            return
        self.hub_top = self.st['zhigh'][0]
        self.hub_h = HUB_T if HUB_T else self.st['tmax'][0]
        if not (self.hub_h > 0):           # a file without that row: fall back
            bare = [q[2] for q in
                    self.section(self.hub_r, *self.factors(self.hub_r))]
            self.hub_h = max(bare) - min(bare)
            self.hub_top = 0.5 * self.hub_h
        self._top = max(q[2] for q in
                        self.section(self.hubtra, *self.factors(self.hubtra)))

    def _unit(self, cam):
        """Camber line scaled to unit height, so the fitted scale is the
        camber-to-chord ratio directly.  A symmetric aerofoil has no camber
        line to scale, so it borrows the parabolic bump instead and the fit
        simply returns zero for it."""
        m = max(abs(v) for v in cam)
        return [v / m for v in cam] if m > 1e-9 else list(self.bump)

    # -- station values, interpolated to any radius -------------------------
    def at(self, key, r):
        """Table value at radius r.  Inside HUBRAD the columns describe the hub
        disc rather than a blade section (CHORD at r=0 is the hub diameter and
        TWIST is driven to zero because the mould parting line has to lie flat
        on the axis), but they are still followed there: they keep the loft
        inside the hub cylinder that swallows it."""
        return interp(r, self.st['r'], self.st[key])

    def profile(self, r):
        """Camber and thickness distributions at radius r, morphed across the
        transition band the file quotes."""
        if self.cam_b is self.cam_a:
            return self.cam_a, self.thk_a
        if self.r_b <= self.r_a:
            w = 0.0 if r < self.r_a else 1.0
        else:
            t = min(1.0, max(0.0, (r - self.r_a) / (self.r_b - self.r_a)))
            w = t * t * (3 - 2 * t)              # smoothstep across the band
        return ([(1 - w) * a + w * b for a, b in zip(self.cam_a, self.cam_b)],
                [(1 - w) * a + w * b for a, b in zip(self.thk_a, self.thk_b)])

    # -- one placed section --------------------------------------------------
    def section(self, r, kt, kc, npts=None):
        """Closed loop of 3D points, TE(upper) -> LE -> TE(lower).

        The section is built about its chord line, which runs from the leading
        edge at (SWEEP, RAKE) down through TWIST.  kt scales the thickness,
        which the file's THICKNESS RATIO already sizes, and kc is the camber as
        a fraction of chord.  The two are independent: thickness sets the area,
        camber sets where the section's centroid sits above the chord line, and
        the file gives a column for each.  Because the surfaces are camber plus
        and minus half the thickness, and the thickness is never negative, the
        section cannot self-intersect whatever the fit asks for.

        npts sets the points per surface.  The section is generated directly on
        a cosine grid of that size rather than by thinning a fixed one: picking
        a subset leaves the points unevenly spaced, and a spline through those
        overshoots badly enough to change the volume by several per cent.
        """
        cam, thk = self.profile(r)
        m = npts or N_PTS
        if m == N_PTS:
            xs, cm, tk, bump = self.xs, cam, thk, self.bump
        else:
            xs = [0.5 * (1 - math.cos(math.pi * i / (m - 1))) for i in range(m)]
            cm = [interp(x, self.xs, cam) for x in xs]
            tk = [interp(x, self.xs, thk) for x in xs]
            bump = [4 * x * (1 - x) for x in xs]

        chord, tr = self.at('chord', r), self.at('tr', r)
        tw = math.radians(self.at('twist', r))
        sweep, rake = self.at('sweep', r), self.rake_at(r)
        te = min(TE_ABS, 0.025 * chord) / chord if chord > 1e-9 else 0.0

        dy, dz = -math.cos(tw), -math.sin(tw)     # LE -> TE
        ny, nz = -math.sin(tw), math.cos(tw)      # section "up"
        up, lo = [], []
        for i in range(m):
            x = xs[i]
            mid = kc * cm[i]                       # camber, as a chord fraction
            half = 0.5 * (max(0.0, kt) * tr * tk[i] + te * x)
            sx = x * chord
            for side, h in ((up, mid + half), (lo, mid - half)):
                hh = h * chord
                side.append((r, sweep + sx * dy + hh * ny, rake + sx * dz + hh * nz))
        lo = self._fair(r, lo)
        if r < self.hub_r:
            up, lo = self._bury(r, up, lo)
        return up[::-1] + lo[1:]                  # TE(upper) -> LE -> TE(lower)

    # -- fit the per-station thickness and camber ----------------------------
    def _fit(self, quiet):
        """Solve, at every station the file gives, for the thickness scale that
        reproduces its CROSS-SECTION area and the camber that puts the section
        centroid where its CG(Y)/CG(Z) columns say.  Area is set by thickness
        alone and the centroid offset by camber alone, so the two solve
        independently, and ZHIGH is left over as a check rather than a target:
        ZHIGH sits at the leading edge on a high-pitch section, where no camber
        change can move it, so fitting to it steers the whole section.

        Outboard of HUBTRA both columns describe a real aerofoil and both are
        used.  Inboard they describe APC's root fairing: the quoted area is
        twice what a section of the quoted thickness could hold, and the CG
        columns put the centroid below the chord line.  There the thickness is
        still fitted, so the root carries the mass the file gives it, but the
        camber is held at its HUBTRA value instead of following the fairing.
        """
        r_all = self.st['r']
        usable = [i for i, r in enumerate(r_all)
                  if r > 0 and self.st['area'][i] > 0
                  and r <= self.r_tip - 0.03]
        self.idx = [i for i in usable if r_all[i] >= self.hubtra - 1e-6]
        if len(self.idx) < 4:                 # odd file: fall back to everything
            self.idx = list(usable)
        if not self.idx:
            raise SystemExit(
                'The station table covers r = %.3f to %.3f in with no usable '
                'cross-section areas.\nThe file looks truncated.'
                % (r_all[0], r_all[-1]))
        kt_l, kc_l, misses = [], [], 0
        for i in self.idx:
            r = r_all[i]
            kt, ok = bisect(
                lambda k: poly_area_centroid(
                    [(p[1], p[2]) for p in self.section(r, k, 0.0)])[0]
                - self.st['area'][i], 0.2, 3.0, 0.1, 12.0)
            misses += (not ok)
            kt_l.append(kt)
            kc_l.append(self._camber(r, kt, i))
        self.r_fit = [r_all[i] for i in self.idx]
        self.kt = smooth(kt_l)
        self.kc = smooth(kc_l)
        self.clamped = []          # trial sections during the fit do not count
        if misses and not quiet:
            print('  note         : %d station fits could not reach the table '
                  'value exactly; closest approach used.' % misses)

    def _camber(self, r, kt, i):
        """Camber-to-chord ratio that puts the section centroid the distance
        off the chord line that the file's CG(Y)/CG(Z) columns imply.  Camber
        shifts the centroid linearly, so two trial sections fix it exactly."""
        tw = math.radians(self.at('twist', r))
        ny, nz = -math.sin(tw), math.cos(tw)
        chord = self.at('chord', r)
        base = (self.at('sweep', r), self.at('rake', r))
        if chord < 1e-9:
            return 0.0

        def off(kc):
            _, cy, cz = poly_area_centroid(
                [(p[1], p[2]) for p in self.section(r, kt, kc)])
            return ((cy - base[0]) * ny + (cz - base[1]) * nz) / chord

        want = ((self.st['cgy'][i] - base[0]) * ny
                + (self.st['cgz'][i] - base[1]) * nz) / chord
        n0, n1 = off(0.0), off(0.05)
        if abs(n1 - n0) < 1e-9:
            return 0.0
        kc = 0.05 * (want - n0) / (n1 - n0)
        return max(-0.15, min(0.15, kc))

    def factors(self, r):
        """Thickness scale and camber at radius r.

        Inside HUBRAD the table's rows are hub, not aerofoil: their area is
        nearly the full chord times thickness, where an aerofoil holds about
        two thirds of that, so fitting an aerofoil to the same area makes it
        half again too deep and it breaks out through the faces of the hub.
        The thickness is therefore capped there at what the hub can hold.  It
        is all buried inside the hub, so only the cap matters, not the shape."""
        return (interp(r, self.r_fit, self.kt), interp(r, self.r_fit, self.kc))

    # -- the spanwise station list used for meshing --------------------------
    def stations(self, n):
        """Radii from inside the hub out to the tip.

        Cosine bunched towards both ends, with every station the file actually
        gives folded in, so that the table's own rows are on the surface rather
        than interpolated past.  It matters most around HUBTRA, where the twist
        turns over inside a couple of rows."""
        r0 = self.st['r'][0] if self.hubless else HUB_INSET * self.hub_r
        r1 = self.r_tip - 0.004
        out = []
        for i in range(n):
            f = i / (n - 1.0)
            f = 0.5 * (1 - math.cos(math.pi * f))      # cosine bunching
            out.append(r0 + (r1 - r0) * f)
        out += [r for r in self.st['r'] if r0 < r < r1]
        out = sorted(out)
        keep = [out[0]]                    # drop near-duplicates: a loft
        for r in out[1:]:                  # through two coincident sections
            if r - keep[-1] > 0.002:       # is degenerate
                keep.append(r)
        return keep

    def loops(self, nsec, npts):
        """The blade as a list of section loops, ready to be stitched."""
        out = []
        for r in self.stations(nsec):
            ku, kl = self.factors(r)
            out.append(self.section(r, ku, kl, npts))
        return out

    def table_volume(self, nblades):
        """Blade volume implied by the file's own CROSS-SECTION column."""
        r0, r1 = 0.0, self.r_tip
        n = 4000
        tot = sum(interp(r0 + (r1 - r0) * (i + 0.5) / n,
                         self.st['r'], self.st['area'])
                  for i in range(n)) * (r1 - r0) / n
        return nblades * tot

    def z_range(self, r_max):
        """Height spanned by the blade root, from where the loft starts out to
        r_max: this is what the hub has to enclose."""
        lo, hi = 1e9, -1e9
        r0 = HUB_INSET * self.hub_r
        for k in range(7):
            r = r0 + (r_max - r0) * k / 6.0
            kt, kc = self.factors(r)
            for _, _, z in self.section(r, kt, kc):
                lo, hi = min(lo, z), max(hi, z)
        return lo, hi

    def check(self):
        """Model vs file at every table station."""
        rows = []
        for i in self.idx:
            r = self.st['r'][i]
            ku, kl = self.factors(r)
            loop = self.section(r, ku, kl)
            a, cy, cz = poly_area_centroid([(p[1], p[2]) for p in loop])
            rows.append((r, self.st['chord'][i], self.st['twist'][i],
                         self.st['area'][i], a,
                         self.st['zhigh'][i], max(p[2] for p in loop),
                         self.st['cgy'][i], cy, self.st['cgz'][i], cz))
        return rows


# ================================================================== meshing
def ear_clip(poly):
    """Triangulate a simple 2D polygon.  Returns index triples."""
    n = len(poly)
    idx = list(range(n))
    area = sum(poly[i][0] * poly[(i + 1) % n][1] - poly[(i + 1) % n][0] * poly[i][1]
               for i in range(n))
    if area < 0:
        idx.reverse()

    def cross(o, a, b):
        return ((poly[a][0] - poly[o][0]) * (poly[b][1] - poly[o][1])
                - (poly[a][1] - poly[o][1]) * (poly[b][0] - poly[o][0]))

    def inside(p, a, b, c):
        d1 = cross(a, b, p)
        d2 = cross(b, c, p)
        d3 = cross(c, a, p)
        return (d1 >= 0 and d2 >= 0 and d3 >= 0) or (d1 <= 0 and d2 <= 0 and d3 <= 0)

    tris, guard = [], 0
    while len(idx) > 3 and guard < 4 * n:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(a, b, c) <= 0:
                continue                                   # reflex
            if any(inside(p, a, b, c) for p in idx if p not in (a, b, c)):
                continue                                   # contains a vertex
            tris.append((a, b, c))
            idx.pop(k)
            guard = 0
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    if len(tris) < n - 2:                                  # degenerate: fan it
        tris = [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)] or tris
    return tris


def loft_mesh(loops):
    """Stitch section loops into a closed surface, capped at both ends."""
    npts = len(loops[0])
    verts, tris = [], []
    for loop in loops:
        verts.extend(loop)
    for s in range(len(loops) - 1):
        a, b = s * npts, (s + 1) * npts
        for i in range(npts):
            j = (i + 1) % npts
            tris.append((a + i, a + j, b + j))
            tris.append((a + i, b + j, b + i))
    for end, base, flip in ((loops[0], 0, True),
                            (loops[-1], (len(loops) - 1) * npts, False)):
        cap = ear_clip([(p[1], p[2]) for p in end])
        for t in cap:
            t = (base + t[0], base + t[1], base + t[2])
            tris.append((t[0], t[2], t[1]) if flip else t)
    return verts, tris


def cylinder_mesh(rad, z0, z1, n, bore=0.0):
    """A closed cylinder, optionally with a concentric bore through it."""
    verts, tris = [], []
    ring = lambda r, z: [(r * math.cos(2 * math.pi * i / n),
                          r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
    ob, ot = 0, n
    verts += ring(rad, z0) + ring(rad, z1)
    for i in range(n):
        j = (i + 1) % n
        tris += [(ob + i, ob + j, ot + j), (ob + i, ot + j, ot + i)]
    if bore > 0:
        ib, it = 2 * n, 3 * n
        verts += ring(bore, z0) + ring(bore, z1)
        for i in range(n):
            j = (i + 1) % n
            tris += [(ib + i, it + j, ib + j), (ib + i, it + i, it + j)]   # inward
            tris += [(ob + i, ib + j, ib + i), (ob + i, ob + j, ib + j)]   # bottom
            tris += [(ot + i, it + i, it + j), (ot + i, it + j, ot + j)]   # top
    else:
        cb, ct = len(verts), len(verts) + 1
        verts += [(0, 0, z0), (0, 0, z1)]
        for i in range(n):
            j = (i + 1) % n
            tris += [(cb, ob + j, ob + i), (ct, ot + i, ot + j)]
    return verts, tris


def hub_mesh(rad, z0, z1, n, edge):
    """A cylinder with rounded top and bottom edges, as a surface of
    revolution.  edge is the round radius."""
    edge = max(0.0, min(edge, 0.49 * (z1 - z0), 0.9 * rad))
    prof = [(0.0, z1)]
    if edge > 0:
        for k in range(7):                      # top round, inside out
            a = math.pi / 2 * (1 - k / 6.0)
            prof.append((rad - edge + edge * math.cos(a), z1 - edge + edge * math.sin(a)))
        for k in range(7):                      # bottom round
            a = -math.pi / 2 * k / 6.0
            prof.append((rad - edge + edge * math.cos(a), z0 + edge + edge * math.sin(a)))
    else:
        prof += [(rad, z1), (rad, z0)]
    prof.append((0.0, z0))
    verts, tris, rings = [], [], []
    for r, z in prof:
        if r <= 1e-12:
            verts.append((0.0, 0.0, z))
            rings.append((len(verts) - 1, None))
        else:
            base = len(verts)
            verts += [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z)
                      for i in range(n)]
            rings.append((base, n))
    for (a, na), (b, nb) in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            if na is None:                      # pole -> ring
                tris.append((a, b + i, b + j))
            elif nb is None:                    # ring -> pole
                tris.append((a + i, b, a + j))
            else:
                tris += [(a + i, a + j, b + j), (a + i, b + j, b + i)]
    return verts, tris


def rotate_z(verts, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [(x * c - y * s, x * s + y * c, z) for x, y, z in verts]


def merge(*meshes):
    verts, tris = [], []
    for v, t in meshes:
        off = len(verts)
        verts.extend(v)
        tris.extend((a + off, b + off, c + off) for a, b, c in t)
    return verts, tris


def scale(verts, f):
    return [(x * f, y * f, z * f) for x, y, z in verts]


def signed_volume(verts, tris):
    tot = 0.0
    for a, b, c in tris:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        tot += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
                + az * (bx * cy - by * cx))
    return tot / 6.0


def orient(verts, tris):
    """Make the winding consistent across each connected shell, then make every
    shell enclose positive volume.  Doing this by propagation means the mesh
    builders above do not have to get their winding right by hand."""
    n = len(tris)
    if not n:
        return tris
    edge = {}
    for ti, (a, b, c) in enumerate(tris):
        for u, v in ((a, b), (b, c), (c, a)):
            edge.setdefault((u, v) if u < v else (v, u), []).append((ti, u, v))
    tris = [tuple(t) for t in tris]
    seen = [False] * n
    for start in range(n):
        if seen[start]:
            continue
        seen[start] = True
        comp, stack = [start], [start]
        while stack:                                  # breadth of one shell
            ti = stack.pop()
            a, b, c = tris[ti]
            for u, v in ((a, b), (b, c), (c, a)):
                for tj, x, y in edge.get((u, v) if u < v else (v, u), ()):
                    if tj == ti or seen[tj]:
                        continue
                    seen[tj] = True
                    # neighbours agree when the shared edge runs the other way
                    if (x, y) == (u, v):
                        p, q, r = tris[tj]
                        tris[tj] = (p, r, q)
                    comp.append(tj)
                    stack.append(tj)
        vol = 0.0
        for ti in comp:
            a, b, c = tris[ti]
            ax, ay, az = verts[a]
            bx, by, bz = verts[b]
            cx, cy, cz = verts[c]
            vol += (ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx)
                    + az * (bx * cy - by * cx))
        if vol < 0:                                   # shell is inside-out
            for ti in comp:
                a, b, c = tris[ti]
                tris[ti] = (a, c, b)
    return tris


def manifold_report(verts, tris):
    """A closed, consistently oriented surface uses every directed edge exactly
    once, so each unordered edge is shared by two faces running opposite ways."""
    seen = {}
    for a, b, c in tris:
        for u, v in ((a, b), (b, c), (c, a)):
            seen[(u, v)] = seen.get((u, v), 0) + 1
    bad = 0
    for (u, v), k in seen.items():
        if k != 1 or seen.get((v, u), 0) != 1:
            bad += 1
    return bad, len(seen)


def clean(verts, tris, tol=1e-9):
    """Weld coincident vertices and drop triangles that collapse to a line."""
    key = {}
    remap = [0] * len(verts)
    out = []
    q = 1.0 / max(tol, 1e-12)
    for i, p in enumerate(verts):
        k = (round(p[0] * q), round(p[1] * q), round(p[2] * q))
        j = key.get(k)
        if j is None:
            j = len(out)
            key[k] = j
            out.append(p)
        remap[i] = j
    tt = []
    for a, b, c in tris:
        a, b, c = remap[a], remap[b], remap[c]
        if a != b and b != c and c != a:
            tt.append((a, b, c))
    return out, tt


def weld_if_safe(verts, tris, tol):
    """Weld coincident vertices, but only keep the result if it did not break
    the topology.  Welding clears the slivers a boolean leaves behind, yet on
    some shapes it fuses two sheets that merely pass close to one another."""
    bad0, _ = manifold_report(verts, tris)
    v2, t2 = clean(verts, tris, tol)
    t2 = orient(v2, t2)
    bad1, _ = manifold_report(v2, t2)
    return (v2, t2) if bad1 <= bad0 else (verts, tris)


def fuse(meshes, have, cut=None):
    """Union the parts, and subtract `cut` if given, via manifold3d when it is
    installed.  Without it the parts are simply concatenated, which leaves the
    blades overlapping at the hub and no bore."""
    if not (have['numpy'] and have['manifold3d']):
        return merge(*meshes), False
    try:
        import numpy as np
        from manifold3d import Manifold, Mesh

        def solid(vt):
            v, t = vt
            return Manifold(Mesh(vert_properties=np.array(v, dtype=np.float32),
                                 tri_verts=np.array(t, dtype=np.uint32)))

        acc = None
        for vt in meshes:
            m = solid(vt)
            acc = m if acc is None else acc + m
        if cut is not None:
            acc = acc - solid(cut)
        mesh = acc.to_mesh()
        verts = [tuple(map(float, p[:3])) for p in mesh.vert_properties]
        tris = [tuple(map(int, t)) for t in mesh.tri_verts]
        return (verts, tris), True
    except BaseException as exc:
        print('  note         : union failed (%s); writing separate shells.'
              % type(exc).__name__)
        return merge(*meshes), False


# ================================================================== exporters
def write_stl(path, verts, tris):
    out = bytearray(struct.pack('<80sI', b'APC propeller rebuild', len(tris)))
    for a, b, c in tris:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        d = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        out += struct.pack('<12fH', nx / d, ny / d, nz / d,
                           ax, ay, az, bx, by, bz, cx, cy, cz, 0)
    with open(path, 'wb') as fh:
        fh.write(out)


def write_obj(path, verts, tris, name):
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('# %s - rebuilt from the APC geometry file, millimetres\n' % name)
        fh.write('o %s\n' % name.replace(' ', '_'))
        for x, y, z in verts:
            fh.write('v %.5f %.5f %.5f\n' % (x, y, z))
        for a, b, c in tris:
            fh.write('f %d %d %d\n' % (a + 1, b + 1, c + 1))


def write_step_faceted(path, verts, tris, name):
    """A STEP part built from planar triangular faces.  Not as good as a NURBS
    solid, but it opens as a solid body in any CAD system and needs nothing
    installed.  Units are millimetres, AP214."""
    out = []
    nid = [0]

    def add(fmt, *args):
        nid[0] += 1
        out.append('#%d=%s;' % (nid[0], (fmt % args) if args else fmt))
        return nid[0]

    # --- units and geometric context, emitted first so their ids are known ---
    mm = add("(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))")
    rad = add("(NAMED_UNIT(*)PLANE_ANGLE_UNIT()SI_UNIT($,.RADIAN.))")
    sr = add("(NAMED_UNIT(*)SI_UNIT($,.STERADIAN.)SOLID_ANGLE_UNIT())")
    unc = add("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-05),#%d,"
              "'distance_accuracy_value','confusion accuracy')", mm)
    ctx = add("(GEOMETRIC_REPRESENTATION_CONTEXT(3)"
              "GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#%d))"
              "GLOBAL_UNIT_ASSIGNED_CONTEXT((#%d,#%d,#%d))"
              "REPRESENTATION_CONTEXT('',''))", unc, mm, rad, sr)
    o = add("CARTESIAN_POINT('',(0.,0.,0.))")
    dz = add("DIRECTION('',(0.,0.,1.))")
    dx = add("DIRECTION('',(1.,0.,0.))")
    origin = add("AXIS2_PLACEMENT_3D('',#%d,#%d,#%d)", o, dz, dx)

    # --- one vertex entity per mesh vertex, shared by every face that uses it -
    vid = []
    for x, y, z in verts:
        p = add("CARTESIAN_POINT('',(%.6f,%.6f,%.6f))" % (x, y, z))
        vid.append(add("VERTEX_POINT('',#%d)", p))

    # --- one edge entity per mesh edge, shared by its two faces --------------
    edge = {}

    def edge_id(u, v):
        key = (u, v) if u < v else (v, u)
        e = edge.get(key)
        if e is None:
            ax, ay, az = verts[key[0]]
            bx, by, bz = verts[key[1]]
            dxx, dyy, dzz = bx - ax, by - ay, bz - az
            d = math.sqrt(dxx * dxx + dyy * dyy + dzz * dzz) or 1.0
            lp = add("CARTESIAN_POINT('',(%.6f,%.6f,%.6f))" % (ax, ay, az))
            ld = add("DIRECTION('',(%.6f,%.6f,%.6f))" % (dxx / d, dyy / d, dzz / d))
            vc = add("VECTOR('',#%d,1.)", ld)
            ln = add("LINE('',#%d,#%d)", lp, vc)
            e = add("EDGE_CURVE('',#%d,#%d,#%d,.T.)", vid[key[0]], vid[key[1]], ln)
            edge[key] = e
        return e, (u < v)

    faces = []
    for a, b, c in tris:
        ax, ay, az = verts[a]
        bx, by, bz = verts[b]
        cx, cy, cz = verts[c]
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        d = math.sqrt(nx * nx + ny * ny + nz * nz)
        if d < 1e-12:
            continue                                   # skip slivers
        nx, ny, nz = nx / d, ny / d, nz / d
        rx, ry, rz = (1.0, 0.0, 0.0) if abs(nx) < 0.9 else (0.0, 1.0, 0.0)
        dot = rx * nx + ry * ny + rz * nz
        rx, ry, rz = rx - dot * nx, ry - dot * ny, rz - dot * nz
        dr = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
        org = add("CARTESIAN_POINT('',(%.6f,%.6f,%.6f))" % (ax, ay, az))
        nd = add("DIRECTION('',(%.6f,%.6f,%.6f))" % (nx, ny, nz))
        rd = add("DIRECTION('',(%.6f,%.6f,%.6f))" % (rx / dr, ry / dr, rz / dr))
        pl = add("PLANE('',#%d)", add("AXIS2_PLACEMENT_3D('',#%d,#%d,#%d)", org, nd, rd))
        oe = []
        for u, v in ((a, b), (b, c), (c, a)):
            e, fwd = edge_id(u, v)
            oe.append(add("ORIENTED_EDGE('',*,*,#%d,%s)", e, '.T.' if fwd else '.F.'))
        lp2 = add("EDGE_LOOP('',(%s))" % ','.join('#%d' % e for e in oe))
        fb = add("FACE_OUTER_BOUND('',#%d,.T.)", lp2)
        faces.append(add("ADVANCED_FACE('',(#%d),#%d,.T.)", fb, pl))

    shell = add("CLOSED_SHELL('',(%s))" % ','.join('#%d' % f for f in faces))
    brep = add("MANIFOLD_SOLID_BREP('%s',#%d)", name, shell)
    shp = add("ADVANCED_BREP_SHAPE_REPRESENTATION('%s',(#%d,#%d),#%d)",
              name, origin, brep, ctx)

    # --- product structure, which most CAD readers insist on -----------------
    appctx = add("APPLICATION_CONTEXT('automotive design')")
    add("APPLICATION_PROTOCOL_DEFINITION('international standard',"
        "'automotive_design',2000,#%d)", appctx)
    pctx = add("PRODUCT_CONTEXT('',#%d,'mechanical')", appctx)
    prod = add("PRODUCT('%s','%s','',(#%d))", name, name, pctx)
    pdf = add("PRODUCT_DEFINITION_FORMATION('','',#%d)", prod)
    pdctx = add("PRODUCT_DEFINITION_CONTEXT('part definition',#%d,'design')", appctx)
    pd = add("PRODUCT_DEFINITION('design','',#%d,#%d)", pdf, pdctx)
    pds = add("PRODUCT_DEFINITION_SHAPE('','',#%d)", pd)
    add("SHAPE_DEFINITION_REPRESENTATION(#%d,#%d)", pds, shp)
    add("PRODUCT_RELATED_PRODUCT_CATEGORY('part','',(#%d))", prod)

    with open(path, 'w', encoding='utf-8') as fh:
        fh.write("ISO-10303-21;\nHEADER;\n"
                 "FILE_DESCRIPTION(('APC propeller rebuild'),'2;1');\n"
                 "FILE_NAME('%s','',('apc_prop.py'),(''),'apc_prop.py','','');\n"
                 "FILE_SCHEMA(('AUTOMOTIVE_DESIGN {1 0 10303 214 1 1 1 1}'));\n"
                 "ENDSEC;\nDATA;\n" % os.path.basename(path))
        fh.write('\n'.join(out))
        fh.write('\nENDSEC;\nEND-ISO-10303-21;\n')


def trim_step_precision(path, digits=6):
    """Round the coordinates a STEP file carries to `digits` significant
    figures.  On a 250 mm part six figures is a quarter of a micron, far below
    anything a propeller cares about, and it takes about a quarter off the file
    size."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            src = fh.read()
        fmt = '%.' + str(digits) + 'g'

        def one(m):
            v = float(m.group(0))
            return '0.' if abs(v) < 1e-9 else (fmt % v)

        out = re.sub(r'-?\d+\.\d{4,}(?:[eE][-+]?\d+)?', one, src)
        if len(out) < len(src):
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(out)
    except BaseException:
        pass                      # size is a nicety; never fail the build for it


def write_step_cadquery(path, blade, nblades, bore_d, z_lo, z_hi, edge,
                        nsec=None, npts=None):
    """A true lofted NURBS solid, when cadquery is installed.  Each blade is
    lofted from just past the centreline, so the blades fuse into the hub that
    the station table already describes; then the bore is cut."""
    import cadquery as cq
    wires = []
    for loop in blade.loops(nsec or STEP_NURBS_SEC, npts or STEP_NURBS_PTS):
        pts = [cq.Vector(x * MM, y * MM, z * MM) for x, y, z in loop]
        params = [i / (len(pts) - 1.0) for i in range(len(pts))]
        surf = cq.Edge.makeSpline(pts, parameters=params, scale=False)
        wires.append(cq.Wire.assembleEdges([surf, cq.Edge.makeLine(pts[-1], pts[0])]))
    # One spline surface per blade side reads as the smoothest body, but it is
    # also a single surface carrying a hundred knot spans, and some CAD kernels
    # would rather have many simple faces.  --step-ruled gives them that.
    solid = cq.Solid.makeLoft(wires, ruled=STEP_RULED)
    if not solid.isValid():
        raise ValueError('loft is not a valid solid')
    if blade.hubless:
        # No hub to fuse to and no bore to cut: the blade loft is the part.
        shape = tighten(solid)
        cq.exporters.export(cq.Workplane('XY').add(shape), path)
        return shape.Volume() / MM ** 3, max_tolerance(shape)
    hub = (cq.Workplane('XY').circle(blade.hub_r * MM)
           .extrude((z_hi - z_lo) * MM).translate((0, 0, z_lo * MM)))
    if edge > 0:
        try:
            hub = hub.edges().fillet(edge * MM)
        except BaseException:
            pass
    blades = [solid.rotate((0, 0, 0), (0, 0, 1), 360.0 * k / nblades)
              for k in range(nblades)]
    # Fuse everything in one operation.  Chaining pairwise unions can silently
    # drop a body when a blade root and the hub meet at a near-tangent face.
    least = 0.9 * nblades * solid.Volume()
    shape = None
    # A fuzzy boolean buys a result by loosening the tolerance carried on every
    # edge and vertex it touches, and that tolerance travels into the STEP file
    # as its stated uncertainty.  A file that says it is only good to a
    # hundredth of a millimetre is one SolidWorks will not knit into a solid.
    # So: exact first, and never looser than a tenth of a micron.
    for tol in (None, 1e-4):
        try:
            cand = (hub.val().fuse(*blades) if tol is None
                    else hub.val().fuse(*blades, tol=tol))
        except BaseException:
            continue
        nsol = len(cand.Solids())
        if cand.Volume() >= least and nsol == 1:
            shape = cand
            break
        if shape is None and cand.Volume() >= least:
            shape = cand                       # keep as a fallback
    if shape is None:
        raise ValueError('union lost a blade')
    if len(shape.Solids()) > 1:
        raise ValueError('union left %d separate bodies' % len(shape.Solids()))
    z_mid, z_pad = 0.5 * (z_lo + z_hi), 0.5 * (z_hi - z_lo) + 0.1 * blade.hub_r
    if not shape.isValid():
        # Two blades that meet through the hub leave near-tangent faces, which
        # OCC's boolean sometimes marks invalid; its own repair pass fixes it.
        try:
            from OCP.ShapeFix import ShapeFix_Shape
            fix = ShapeFix_Shape(shape.wrapped)
            fix.SetPrecision(1e-6)
            fix.SetMaxTolerance(1e-4)
            fix.Perform()
            repaired = cq.Shape.cast(fix.Shape())
            if repaired.isValid() and repaired.Volume() > 0:
                shape = repaired
        except BaseException:
            pass
    shape = shape.cut(cq.Workplane('XY').circle(bore_d / 2 * MM)
                      .extrude(4 * z_pad * MM)
                      .translate((0, 0, z_mid * MM - 2 * z_pad * MM)).val())
    if not shape.isValid() or shape.Volume() <= 0:
        raise ValueError('fused solid is not valid')
    shape = blend_root(shape, z_hi)
    if not shape.isValid() or shape.Volume() <= 0:
        raise ValueError('fused solid is not valid')
    shape = tighten(shape)
    cq.exporters.export(cq.Workplane('XY').add(shape), path)
    return shape.Volume() / MM ** 3, max_tolerance(shape)


def blend_root(shape, z_top):
    """Round the seam where the blade breaks out of the top face of the hub.

    The file says the root carries about twice the area an aerofoil of its
    chord and thickness holds, and the difference is the moulded fillet.  A
    radius here is not that fillet, and it recovers little of the volume, but
    it does remove the crease the boolean leaves along the hub face, which is
    the part that would trip a mesher.  The underside seam is left alone: the
    blade leaves the hub there at a shallow angle and a fillet on it fails as
    often as it works."""
    if ROOT_BLEND <= 0:
        return shape
    try:
        import cadquery as cq
        seams, seen = [], []
        for face in shape.Faces():
            if face.geomType() != 'PLANE' or abs(face.Center().z - z_top * MM) > 1e-4:
                continue
            for e in face.Edges():
                if e.geomType() == 'BSPLINE' and not any(e.isSame(x) for x in seen):
                    seen.append(e)
                    seams.append(e)
        if not seams:
            return shape
        out = cq.Shape.cast(shape.wrapped).Solids()[0].fillet(ROOT_BLEND, seams)
        if out.isValid() and len(out.Solids()) == 1 and out.Volume() > shape.Volume():
            return out
    except BaseException:
        pass
    return shape


def max_tolerance(shape):
    """Largest tolerance carried by any face, edge or vertex, in mm.  This is
    the number a STEP file reports as its uncertainty, and the one a CAD
    package uses to decide whether the faces really meet."""
    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX, TopAbs_FACE
        from OCP.BRep import BRep_Tool
        from OCP.TopoDS import TopoDS
        worst = 0.0
        for kind, cast in ((TopAbs_FACE, TopoDS.Face_s),
                           (TopAbs_EDGE, TopoDS.Edge_s),
                           (TopAbs_VERTEX, TopoDS.Vertex_s)):
            ex = TopExp_Explorer(shape.wrapped, kind)
            while ex.More():
                worst = max(worst, BRep_Tool.Tolerance_s(cast(ex.Current())))
                ex.Next()
        return worst
    except BaseException:
        return float('nan')


def tighten(shape, target=1e-6):
    """Pull edge and vertex tolerances back down after the booleans.

    OpenCascade widens them as it works, and whatever is left over is written
    into the STEP file as the uncertainty of the whole model.  Shrinking them
    can leave a shape that no longer closes, so the result is kept only if it
    is still a single valid solid of the same volume."""
    try:
        import cadquery as cq
        from OCP.ShapeFix import ShapeFix_ShapeTolerance
        from OCP.BRepLib import BRepLib
        before = shape.Volume()
        for limit in (target, 1e-5, 1e-4):
            work = cq.Shape.cast(shape.wrapped.Complemented().Complemented())
            ShapeFix_ShapeTolerance().LimitTolerance(work.wrapped, 0.0, limit)
            BRepLib.SameParameter_s(work.wrapped, limit, True)
            if (work.isValid() and len(work.Solids()) == 1
                    and abs(work.Volume() - before) < 1e-6 * max(1.0, before)):
                return work
    except BaseException:
        pass
    return shape


VIEWER_HTML = r"""<title>APC 7x4 Rebuild</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#eef0ee; --panel:#f8f9f7; --ink:#1c2023; --muted:#5d6570; --line:#cfd4d0;
  --accent:#1f6f7a; --accent-ink:#ffffff; --le:#d9822b;
  --scene:#e4e7e4; --mesh:#b9bfc4;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#15181b; --panel:#1d2126; --ink:#e6e9ea; --muted:#9aa3ab; --line:#333a40;
    --accent:#4fb3bf; --accent-ink:#0f1a1c; --le:#e7a054;
    --scene:#1a1e22; --mesh:#8f979e;
  }
}
:root[data-theme="dark"]{
  --bg:#15181b; --panel:#1d2126; --ink:#e6e9ea; --muted:#9aa3ab; --line:#333a40;
  --accent:#4fb3bf; --accent-ink:#0f1a1c; --le:#e7a054;
  --scene:#1a1e22; --mesh:#8f979e;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px;line-height:1.45}
header{display:flex;align-items:baseline;gap:16px;padding:14px 20px 10px;border-bottom:1px solid var(--line)}
header h1{font-size:18px;font-weight:600;margin:0;letter-spacing:-0.01em}
header .sub{color:var(--muted);font-size:13px}
.wrap{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:0;height:calc(100vh - 52px)}
@media (max-width:900px){.wrap{grid-template-columns:1fr;grid-template-rows:60vh 1fr;height:auto}}
.scene{position:relative;background:var(--scene);min-height:0;min-width:0}
.scene canvas{display:block;width:100%;height:100%}
.hud{position:absolute;left:12px;top:12px;display:flex;flex-wrap:wrap;gap:6px}
.hud button, .hud label{font:inherit;font-size:12px;padding:5px 10px;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:4px;cursor:pointer}
.hud button:hover{border-color:var(--accent)}
.hud button:focus-visible,.hud label:focus-within{outline:2px solid var(--accent);outline-offset:1px}
.hud label{display:inline-flex;align-items:center;gap:6px}
.hint{position:absolute;right:12px;bottom:10px;font-size:11px;color:var(--muted)}
.axes{position:absolute;left:12px;bottom:10px;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11px;color:var(--muted)}
.panel{background:var(--panel);border-left:1px solid var(--line);padding:16px 18px;overflow:auto;min-height:0}
@media (max-width:900px){.panel{border-left:0;border-top:1px solid var(--line)}}
.panel h2{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--muted);margin:18px 0 8px}
.panel h2:first-child{margin-top:0}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0;font-variant-numeric:tabular-nums}
dt{color:var(--muted)}
dd{margin:0;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px}
table{border-collapse:collapse;width:100%;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:12px;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:3px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-weight:500;color:var(--muted)}
th:first-child,td:first-child{text-align:left}
.tbl{overflow-x:auto}
p.note{color:var(--muted);font-size:12px;margin:8px 0 0}
.ok{color:var(--accent)}
</style>

<header>
  <h1 id="ttl">Propeller rebuild</h1>
  <span class="sub" id="src"></span>
</header>

<div class="wrap">
  <div class="scene" id="scene">
    <canvas id="c"></canvas>
    <div class="hud">
      <button data-view="iso">Isometric</button>
      <button data-view="top">Thrust side (+Z)</button>
      <button data-view="bottom">Back side</button>
      <button data-view="front">Edge on (−Y)</button>
      <button data-view="tip">Along blade (+X)</button>
      <label><input type="checkbox" id="wire"> Wireframe</label>
      <label><input type="checkbox" id="spin"> Spin</label>
    </div>
    <div class="axes">X radial · Y fore-aft (LE side +Y) · Z thrust</div>
    <div class="hint">Drag to orbit · wheel to zoom · shift-drag to pan</div>
  </div>

  <aside class="panel">
    <h2>Propeller</h2>
    <dl id="spec"></dl>

    <h2>Model vs file</h2>
    <dl id="stats"></dl>
    <p class="note">Each lofted section was fitted so its area and highest point match the CROSS-SECTION and ZHIGH columns; the CGY and CGZ columns then serve as an independent check.</p>

    <h2>Section check (in)</h2>
    <div class="tbl">
    <table>
      <thead><tr><th>r</th><th>chord</th><th>twist°</th><th>CGY file</th><th>model</th><th>CGZ file</th><th>model</th></tr></thead>
      <tbody id="vt"></tbody>
    </table>
    </div>
  </aside>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const VERTS_B64 = "__VERTS__";
const FACES_B64 = "__FACES__";
const WIDE = __WIDE__;
const M = __META__;
const VERIFY = M.verify;

function b64ToBytes(s){const bin=atob(s);const u=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u[i]=bin.charCodeAt(i);return u;}
const verts=new Float32Array(b64ToBytes(VERTS_B64).buffer);
const faces=WIDE?new Uint32Array(b64ToBytes(FACES_B64).buffer)
                :new Uint16Array(b64ToBytes(FACES_B64).buffer);

// ---- header and side panel from the build summary ----
const f2=(x,n)=>Number(x).toFixed(n);
document.title=M.name+' rebuild';
document.getElementById('ttl').textContent=M.name+' rebuild';
document.getElementById('src').textContent=
  'Solid rebuilt from the APC PERF geometry table ('+M.source+'). Model units mm; table values in inches as in the source.';
function putRows(id,rows){document.getElementById(id).innerHTML=
  rows.map(([k,v])=>`<dt>${k}</dt><dd>${v}</dd>`).join('');}
putRows('spec',[
  ['Diameter',`${f2(M.diameter_in,2)} in (${f2(M.diameter_in*25.4,1)} mm)`],
  ['Quoted pitch',`${f2(M.pitch_in,2)} in`],
  ['Blades',M.blades],
  ['Hub radius',`${f2(M.hub_r_in,2)} in (file)`],
  ['Hub thickness',`${f2(M.hub_h_in,2)} in (file)`],
  ['Bore',`${f2(M.bore_in,2)} in (assumed)`],
  ['Section',(M.airfoil||'Clark-Y')+', thickness-scaled'],
  ['Rotation','anticlockwise seen from +Z'],
]);
putRows('stats', M.fused ? [
  ['Volume',`${f2(M.model_vol_in3,3)} vs ${f2(M.file_vol_in3,3)} in³`],
  [`Mass (SG ${f2(M.sg,2)})`,`${f2(M.model_mass_g,1)} vs ${f2(M.file_mass_g,1)} g`],
] : [
  ['Volume',`file quotes ${f2(M.file_vol_in3,3)} in³`],
  [`Mass (SG ${f2(M.sg,2)})`,`file quotes ${f2(M.file_mass_g,1)} g`],
  ['Note','blades and hub are separate shells here'],
]);

const css=getComputedStyle(document.documentElement);
const col=n=>new THREE.Color(css.getPropertyValue(n).trim());

const canvas=document.getElementById('c');
const sceneEl=document.getElementById('scene');
const renderer=new THREE.WebGLRenderer({canvas,antialias:true});
renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
const scene=new THREE.Scene();
scene.background=col('--scene');
const camera=new THREE.PerspectiveCamera(35,1,1,2000);

const geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(verts,3));
geo.setIndex(new THREE.BufferAttribute(faces,1));
geo.computeVertexNormals();
const mat=new THREE.MeshStandardMaterial({color:col('--mesh'),metalness:0.05,roughness:0.55,side:THREE.DoubleSide});
const mesh=new THREE.Mesh(geo,mat);
scene.add(mesh);
const wireMat=new THREE.MeshBasicMaterial({color:col('--accent'),wireframe:true,transparent:true,opacity:0.35});
const wire=new THREE.Mesh(geo,wireMat); wire.visible=false; scene.add(wire);

// axes triad (X red-ish radial, Y fore-aft, Z thrust) drawn with theme accent + LE colour
const axes=new THREE.Group();
function axis(dir,color,len){const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0),dir.clone().multiplyScalar(len)]);axes.add(new THREE.Line(g,new THREE.LineBasicMaterial({color})));}
// frame from the model's own bounds, so any propeller fills the view
const bmin=[1e30,1e30,1e30], bmax=[-1e30,-1e30,-1e30];
for(let i=0;i<verts.length;i+=3)for(let k=0;k<3;k++){
  const q=verts[i+k]; if(q<bmin[k])bmin[k]=q; if(q>bmax[k])bmax[k]=q;}
const CTR=[0,1,2].map(k=>0.5*(bmin[k]+bmax[k]));
const RAD=0.5*Math.hypot(bmax[0]-bmin[0],bmax[1]-bmin[1],bmax[2]-bmin[2])||1;
axis(new THREE.Vector3(1,0,0),col('--le'),0.28*RAD);
axis(new THREE.Vector3(0,1,0),col('--accent'),0.28*RAD);
axis(new THREE.Vector3(0,0,1),col('--ink'),0.28*RAD);
axes.position.set(-1.05*RAD,-0.30*RAD,-0.12*RAD);
scene.add(axes);

scene.add(new THREE.HemisphereLight(0xffffff,0x334455,0.9));
const key=new THREE.DirectionalLight(0xffffff,0.8); key.position.set(60,-80,120); scene.add(key);
const fill=new THREE.DirectionalLight(0xffffff,0.35); fill.position.set(-80,60,-40); scene.add(fill);

// simple orbit: spherical coords about target
let R0=3*RAD;
let target=new THREE.Vector3(CTR[0],CTR[1],CTR[2]), radius=R0, theta=-0.9, phi=1.05;
const up=new THREE.Vector3(0,0,1); camera.up.copy(up);
function updateCamera(){
  const x=target.x+radius*Math.sin(phi)*Math.cos(theta);
  const y=target.y+radius*Math.sin(phi)*Math.sin(theta);
  const z=target.z+radius*Math.cos(phi);
  camera.position.set(x,y,z); camera.lookAt(target);
}
const views={
  iso:{theta:-0.9,phi:1.05,mult:1},
  top:{theta:-Math.PI/2,phi:0.001,mult:1},
  bottom:{theta:-Math.PI/2,phi:Math.PI-0.001,mult:1},
  front:{theta:-Math.PI/2,phi:Math.PI/2,mult:1},
  tip:{theta:0,phi:Math.PI/2,mult:0.45},
};
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{const v=views[b.dataset.view];theta=v.theta;phi=v.phi;radius=R0*v.mult;target.set(CTR[0],CTR[1],CTR[2]);updateCamera();}));
document.getElementById('wire').addEventListener('change',e=>{wire.visible=e.target.checked;});
const spinBox=document.getElementById('spin');

let drag=null;
canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY,shift:e.shiftKey};canvas.setPointerCapture(e.pointerId);});
canvas.addEventListener('pointermove',e=>{
  if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
  if(drag.shift||e.buttons===4){
    const right=new THREE.Vector3().crossVectors(camera.getWorldDirection(new THREE.Vector3()),up).normalize();
    const upv=new THREE.Vector3().crossVectors(right,camera.getWorldDirection(new THREE.Vector3())).normalize();
    const s=radius*0.0015; target.addScaledVector(right,-dx*s); target.addScaledVector(upv,dy*s);
  } else { theta-=dx*0.006; phi=Math.min(Math.PI-0.01,Math.max(0.01,phi-dy*0.006)); }
  updateCamera();
});
canvas.addEventListener('pointerup',()=>drag=null);
canvas.addEventListener('wheel',e=>{e.preventDefault();radius*=Math.exp(e.deltaY*0.0012);radius=Math.min(16*RAD,Math.max(0.05*RAD,radius));updateCamera();},{passive:false});

function resize(){
  const w=sceneEl.clientWidth||1,h=sceneEl.clientHeight||1;
  renderer.setSize(w,h,false); camera.aspect=w/h; camera.updateProjectionMatrix();
  const vf=camera.fov*Math.PI/180, hf=2*Math.atan(Math.tan(vf/2)*camera.aspect);
  R0=1.12*RAD/Math.sin(Math.min(vf,hf)/2);        // always frames the model
}
window.addEventListener('resize',resize); resize(); radius=R0; updateCamera();
const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
function loop(){ if(spinBox.checked&&!reduced){mesh.rotation.z+=0.01;wire.rotation.z=mesh.rotation.z;} renderer.render(scene,camera); requestAnimationFrame(loop);} loop();

// verification table
const tb=document.getElementById('vt');
for(const r of VERIFY){const tr=document.createElement('tr');tr.innerHTML=r.map((v,i)=>`<td>${i===2?v.toFixed(1):v.toFixed(i===0?3:4)}</td>`).join('');tb.appendChild(tr);}
</script>
"""


def write_viewer(path, verts, tris, meta, rows):
    """A self-contained HTML page with the mesh embedded.  Only three.js is
    fetched from a CDN; everything else is inline, so the file works from a
    local folder, an email attachment or a shared drive."""
    vb = bytearray()
    for x, y, z in verts:
        vb += struct.pack('<3f', x, y, z)
    wide = len(verts) >= 65536
    fb = bytearray()
    for t in tris:
        fb += struct.pack('<3I' if wide else '<3H', *t)
    step = max(1, len(rows) // 16)
    tbl = [[round(v, 4) for v in (r[0], r[1], r[2], r[7], r[8], r[9], r[10])]
           for i, r in enumerate(rows) if i % step == 0]
    js = dict(meta)
    js['verify'] = tbl
    html = (VIEWER_HTML
            .replace('__VERTS__', base64.b64encode(bytes(vb)).decode())
            .replace('__FACES__', base64.b64encode(bytes(fb)).decode())
            .replace('__WIDE__', 'true' if wide else 'false')
            .replace('__META__', json_dump(js)))
    # A complete document with an explicit charset, and written as UTF-8: on
    # Windows the default encoding is cp1252, which has no minus sign.
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('<!doctype html>\n<html lang="en">\n<head>\n'
                 '<meta charset="utf-8">\n'
                 '<meta name="viewport" content="width=device-width,'
                 'initial-scale=1">\n')
        fh.write(html)
        fh.write('\n</html>\n')


def json_dump(obj):
    """Small JSON writer, so the script needs no json import for this either."""
    if isinstance(obj, dict):
        return '{' + ','.join('%s:%s' % (json_dump(str(k)), json_dump(v))
                              for k, v in obj.items()) + '}'
    if isinstance(obj, (list, tuple)):
        return '[' + ','.join(json_dump(v) for v in obj) + ']'
    if isinstance(obj, bool):
        return 'true' if obj else 'false'
    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and (obj != obj or obj in (float('inf'), float('-inf'))):
            return 'null'
        return repr(obj)
    if obj is None:
        return 'null'
    return '"' + str(obj).replace('\\', '\\\\').replace('"', '\\"') + '"'


# ======================================================================= main
def build(path, outdir='.', quiet=False, formats=FORMATS, log=print):
    have = probe()
    txt = read_text(path)
    st = load_stations(txt, path)
    hdr = load_header(txt, path)
    log('%s: radius %.2f in, %d blades, hub radius %.3f in'
        % (hdr['name'], st['r'][-1], hdr['blades'], hdr['hub_r'] or 0))
    if not quiet:
        report(have, verbose=True)

    blade = Blade(st, hdr, quiet)
    nb, hub_r, bore = hdr['blades'], blade.hub_r, blade.bore
    # The hub is the disc the table's r=0 row describes: MAX-THICK thick with
    # its top face at ZHIGH.  Sections lofted inside HUBRAD are shrunk to sit
    # within it, so it needs no room beyond its own size.
    hub_h = blade.hub_h
    zhi = blade.hub_top
    zlo = zhi - hub_h
    edge = HUB_EDGE * 0.5 * hub_h
    if blade.hubless:
        nb, bore = 1, 0.0
        log('  hub          : none.  This file has no HUBRAD and its table '
            'starts at HUBTRA (%.3f in), which is how APC supply a folding '
            'blade: the hub is a separate part.  One blade is written, capped '
            'at its root, with no bore.' % blade.hub_r)
    else:
        log('  hub          : %.3f in across (file), %.3f in / %.2f mm thick '
            '(%s), %.3f in / %.2f mm bore (%s)'
            % (2 * hub_r, hub_h, hub_h * MM, 'set' if HUB_T else 'file',
               bore, bore * MM, 'set' if BORE_D else 'assumed'))
    zpad = 0.5 * hub_h + 0.1 * hub_r

    def assemble(nsec, npts, facets):
        """The blades, lofted and fused, with the bore drilled through."""
        v, t = clean(*loft_mesh(blade.loops(nsec, npts)))
        t = orient(v, t)
        parts = [(scale(rotate_z(v, 360.0 * k / nb), MM), t) for k in range(nb)]
        drill = None
        if not blade.hubless:
            hv, ht = clean(*hub_mesh(hub_r, zlo, zhi, facets, edge))
            parts.append((scale(hv, MM), orient(hv, ht)))
            mid = 0.5 * (zlo + zhi)
            drill = clean(*cylinder_mesh(bore / 2 * MM, (mid - zpad) * MM,
                                         (mid + zpad) * MM, facets))
            drill = (drill[0], orient(*drill))
        (vv, tt), ok = fuse(parts, have, cut=drill)
        vv, tt = weld_if_safe(vv, tt, WELD_MM)
        return vv, orient(vv, tt), ok
    base = os.path.join(outdir, 'APC_' + ''.join(
        c if c.isalnum() or c in '.-' else '_' for c in hdr['name']))

    # ---- mesh, in millimetres -------------------------------------------
    verts, tris, fused = assemble(MESH_SEC, MESH_PTS, HUB_FACETS)

    bad, nedge = manifold_report(verts, tris)
    vol = signed_volume(verts, tris) / MM ** 3
    if blade.clamped:
        log('  note         : lower surface clamped against the upper at '
              'r >= %.3f in' % min(blade.clamped))
    log('  mesh         : %d triangles, %s' % (
        len(tris), 'watertight' if bad == 0 else '%d of %d edges not shared by '
        'exactly 2 faces' % (bad, nedge)))
    tbl_vol = blade.table_volume(nb)
    if fused:
        log('  volume       : model %.4f in^3 with the bore cut; file quotes '
            '%.4f in^3' % (vol, hdr['file_vol']))
        log('  mass         : %.2f g at SG %.2f' % (vol * MM ** 3 * 1e-3 * hdr['sg'],
                                                      hdr['sg']))
    else:
        log('  volume       : blades and hub are separate shells and the bore '
            'is not cut, so the summed %.4f in^3 is not comparable with the '
            '%.4f in^3 quoted' % (vol, hdr['file_vol']))

    made = []
    if 'stl' in formats:
        write_stl(base + '.stl', verts, tris)
        made.append('stl')
    if 'obj' in formats:
        write_obj(base + '.obj', verts, tris, hdr['name'])
        made.append('obj')
    if made:
        log('  wrote        : %s' % ', '.join(base + '.' + e for e in made))

    # ---- STEP -------------------------------------------------------------
    step_kind = 'faceted'
    if 'step' not in formats:
        have['cadquery'] = None
    if have['cadquery']:
        ins0 = HUB_INSET
        for ins in (ins0, 0.8, 0.9, 0.4):
            # A near-tangent contact where a blade enters the hub can defeat
            # the boolean; moving where the loft starts inside the hub gives
            # it a differently conditioned intersection to work with.
            globals()['HUB_INSET'] = ins
            try:
                v, tol = write_step_cadquery(base + '.step', blade, nb, bore,
                                             zlo, zhi, edge)
                step_kind = 'NURBS solid, %.4f in^3, tolerance %.0e mm' % (v, tol)
                if tol > 1e-4:
                    raise ValueError('solid carries a %.0e mm tolerance; a CAD '
                                     'package will not knit it' % tol)
                break
            except BaseException as exc:
                last = exc
        else:
            log('  note         : cadquery STEP failed (%s: %s); '
                'falling back to faceted.' % (type(last).__name__, last))
            have['cadquery'] = False
        globals()['HUB_INSET'] = ins0
    if have['cadquery'] is False:
        sav, sat, _ = assemble(STEP_SEC, STEP_PTS, 32)
        write_step_faceted(base + '.step', sav, sat, hdr['name'])
        trim_step_precision(base + '.step')
        step_kind = 'faceted, %d facets' % len(sat)
    if have['cadquery'] is not None:
        log('  wrote        : %s.step (%s)' % (base, step_kind))

    # ---- viewer -----------------------------------------------------------
    if 'html' not in formats:
        return base
    vev, vet, _ = assemble(VIEW_SEC, VIEW_PTS, 48)
    meta = dict(name=hdr['name'], source=hdr['source'],
                radius=st['r'][-1], diameter_in=2 * st['r'][-1],
                pitch_in=max(st['pitch_q']), blades=nb,
                hub_r_in=hub_r, hub_h_in=hub_h, bore_in=bore, sg=hdr['sg'],
                airfoil=blade.name_a if blade.name_b == blade.name_a
                else '%s to %s' % (blade.name_a, blade.name_b),
                model_vol_in3=vol if fused else float('nan'),
                file_vol_in3=tbl_vol,
                model_mass_g=vol * MM ** 3 * 1e-3 * hdr['sg'] if fused else float('nan'),
                file_mass_g=hdr['file_mass_g'], fused=fused)
    write_viewer(base + '.html', vev, vet, meta, blade.check())
    log('  wrote        : %s.html  (open it in any browser)' % base)
    return base


def build_folder(folder, outdir, formats, resume=False, split=False):
    """Every geometry file in a folder, one model each, with a summary.

    With split, each propeller gets a folder of its own holding its outputs and
    a copy of the geometry file they came from, so a folder can be handed on by
    itself and still say where it came from."""
    names = sorted(f for f in os.listdir(folder)
                   if os.path.splitext(f)[1].lower() in ('.pe0', '.txt', '.dat'))
    if not names:
        raise SystemExit('No .PE0 files in %s' % folder)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    report(probe())
    print('%d files -> %s\n' % (len(names), outdir))
    rows, done, skipped, failed = [], 0, [], []
    t0 = time.time()
    for i, name in enumerate(names, 1):
        src = os.path.join(folder, name)
        try:
            head = read_text(src).splitlines()[0].split('(')[0].strip()
        except BaseException:
            head = ''
        tag = ''.join(c if c.isalnum() or c in '.-' else '_' for c in head)
        here = os.path.join(outdir, tag) if (split and tag) else outdir
        if resume:
            base = os.path.join(here, 'APC_' + tag)
            if head and all(os.path.exists(base + '.' + e) for e in formats):
                done += 1
                continue
        lines = []
        try:
            if here != outdir and not os.path.isdir(here):
                os.makedirs(here)
            build(src, here, quiet=True, formats=formats, log=lines.append)
            if here != outdir:
                with open(src, 'rb') as fh:
                    blob = fh.read()
                with open(os.path.join(here, name), 'wb') as fh:
                    fh.write(blob)
            done += 1
            head = lines[0] if lines else name
            vol = [l for l in lines if 'volume' in l]
            rows.append((name, head, vol[0].split(':', 1)[1].strip() if vol else ''))
            note = [l.split(':', 1)[1].strip() for l in lines if 'note' in l]
            print('[%3d/%d] %-24s %s%s' % (i, len(names), name, head.split(':')[0],
                                           '  (' + '; '.join(note) + ')' if note else ''))
        except SystemExit as exc:
            skipped.append((name, str(exc).splitlines()[0]))
            print('[%3d/%d] %-24s SKIPPED  %s' % (i, len(names), name,
                                                  str(exc).splitlines()[0][:70]))
        except BaseException as exc:
            failed.append((name, '%s: %s' % (type(exc).__name__, exc)))
            print('[%3d/%d] %-24s FAILED   %s: %s' % (i, len(names), name,
                                                      type(exc).__name__, exc))
        sys.stdout.flush()
    with open(os.path.join(outdir, 'summary.csv'), 'w', encoding='utf-8') as fh:
        fh.write('file,propeller,volume\n')
        for name, head, vol in rows:
            fh.write('"%s","%s","%s"\n' % (name, head.replace('"', "'"),
                                            vol.replace('"', "'")))
        for name, why in skipped:
            fh.write('"%s","SKIPPED","%s"\n' % (name, why.replace('"', "'")))
        for name, why in failed:
            fh.write('"%s","FAILED","%s"\n' % (name, why.replace('"', "'")))
    print('\n%d built, %d skipped, %d failed, in %.1f min'
          % (done, len(skipped), len(failed), (time.time() - t0) / 60.0))
    if skipped:
        print('skipped (no usable station table in the file):')
        for name, _ in skipped:
            print('   ', name)
    if failed:
        print('failed:')
        for name, why in failed:
            print('   ', name, '-', why)
    print('summary written to %s' % os.path.join(outdir, 'summary.csv'))
    return outdir


def length_in(text, flag=''):
    """A length from the command line, in inches.

    APC's files are in inches and everything written out is in millimetres, so
    a bare number is ambiguous and a wrong guess is silent.  Units are
    therefore accepted and encouraged: 10mm, 0.4in, 0.4".  A bare number is
    read as inches, which is the unit the file itself uses."""
    t = text.strip().lower().replace('"', 'in').replace("'", 'in')
    scale = 1.0
    for suffix, factor in (('mm', 1.0 / MM), ('cm', 10.0 / MM), ('in', 1.0)):
        if t.endswith(suffix):
            t, scale = t[:-len(suffix)].strip(), factor
            break
    try:
        v = float(t) * scale
    except ValueError:
        raise SystemExit('%s: could not read a length from %r.  Write it as '
                         '10mm, 0.4in, or a bare number meaning inches.'
                         % (flag or 'length', text))
    if not (v > 0):
        raise SystemExit('%s: a length has to be positive.' % (flag or 'length'))
    return v


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('-')]
    flags = set(a for a in argv[1:] if a.startswith('-'))
    if '--check' in flags or '-c' in flags:
        print('apc_prop.py environment check')
        report(probe())
        print('\nNothing above is required - the script runs without any of it.')
        return 0
    resume = '--resume' in flags
    flags.discard('--resume')
    split = '--split' in flags
    flags.discard('--split')
    if '-h' in flags or '--help' in flags or not args:
        print(__doc__)
        return 0 if not flags - {'-h', '--help'} else 2
    formats = FORMATS
    for f in list(flags):
        if f.startswith('--mesh='):
            a, b = f.split('=', 1)[1].split(',')
            globals()['MESH_SEC'], globals()['MESH_PTS'] = int(a), int(b)
            flags.discard(f)
        elif f.startswith('--step='):
            a, b = f.split('=', 1)[1].split(',')
            globals()['STEP_NURBS_SEC'], globals()['STEP_NURBS_PTS'] = int(a), int(b)
            flags.discard(f)
        elif f.startswith('--root-blend='):
            globals()['ROOT_BLEND'] = float(f.split('=', 1)[1])
            flags.discard(f)
        elif f == '--step-ruled':
            globals()['STEP_RULED'] = True
            flags.discard(f)
        elif f.startswith('--hub-thickness='):
            globals()['HUB_T'] = length_in(f.split('=', 1)[1], f)
            flags.discard(f)
        elif f.startswith('--bore='):
            globals()['BORE_D'] = length_in(f.split('=', 1)[1], f)
            flags.discard(f)
        elif f.startswith('--formats='):
            formats = tuple(x.strip().lower() for x in f.split('=', 1)[1].split(','))
            flags.discard(f)
    src = args[0]
    if os.path.isdir(src):
        out = args[1] if len(args) > 1 else os.path.join(src, 'models')
        try:
            build_folder(src, out, formats, resume=resume, split=split)
        except SystemExit:
            raise
        except BaseException as exc:
            print('\nFailed: %s: %s' % (type(exc).__name__, exc), file=sys.stderr)
            return 1
        return 0
    if not os.path.exists(src):
        print('Cannot find "%s".\nRun it as:  python apc_prop.py path/to/7x4.PE0'
              % src, file=sys.stderr)
        return 1
    try:
        build(src, args[1] if len(args) > 1 else '.', formats=formats)
    except SystemExit:
        raise
    except BaseException as exc:
        print('\nFailed: %s: %s' % (type(exc).__name__, exc), file=sys.stderr)
        print('Run "python apc_prop.py --check" and send that output along with '
              'this message.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
