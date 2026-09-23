APC propeller models, all 450 files in the archive
==================================================

One folder per propeller. Each holds the geometry file it was built from and
four outputs:

    <name>-PERF.PE0    the source geometry file, copied in
    APC_<name>.stl     binary STL, millimetres
    APC_<name>.obj     Wavefront OBJ, millimetres
    APC_<name>.step    STEP solid, ruled patch loft, millimetres
    APC_<name>.html    self-contained viewer; open in any browser

Built with:  python apc_prop.py <folder> ALL_PROPS --split --step-ruled

MANIFEST.csv lists every propeller with its diameter, pitch, hub thickness,
bore, model volume, the volume the file quotes, and the difference.

Two kinds of model
------------------
432 of them are a hub with its blades on it, bored through.

18 are a single blade with no hub, capped at its root. Those files carry no
HUBRAD and their station table starts at HUBTRA, which is how APC supply a
folding blade: the hub is a separate part you buy separately. Writing one blade
is the honest reading of that data. They are the F and MRF models plus the
15x12E, and MANIFEST.csv marks them "one blade, no hub". Their volume is not
compared with the file's figure, because the file quotes the whole propeller
including a hub that is not in the data.

How close these are
-------------------
Volume against the figure each file quotes, over the 432 with hubs:

    median          -7.3%
    within +/-10%    272 of 432
    range           -36.3% to +4.8%

The models are light, never heavy, and always for the same reason: the moulded
fillet where the blade swells into the hub. Inboard of HUBTRA the file's
CROSS-SECTION column is about twice what an aerofoil of the quoted chord and
thickness can hold, and no lofted aerofoil section carries that. It costs most
on the smallest propellers, where the root is a larger share of the whole: the
5 to 5.5 inch E series are 35% light, while a 10 inch is nearer 3%.

The blade itself is not approximate in the same way. Section area is fitted to
CROSS-SECTION at every station and matches within 0.4%, camber is fitted to
CG(Y) and CG(Z), and ZHIGH, which is not fitted, lands within about 0.006 in.
Read README.md in the toolkit for the detail.

What to check before using one
------------------------------
The bore is a guess. There is no bore column in the file, so it is picked from
hub size, and it will be wrong on some models: the 7x9E for instance is really
5 mm where the guess picks 1/4 in. Rebuild that one propeller with
--bore=5mm if the bore matters to you.

Hub thickness comes from MAX-THICK at r=0, which is the disc itself. It is not
the hub thickness on APC's product page, which is the overall depth of the part
around the hub. Both figures are in MANIFEST.csv terms consistent: build the
disc from the table, add the root, and the overall depth agrees with the
published number to about 0.01 in.

Every STEP is a single valid solid, checked on reimport, with a worst tolerance
of 1e-06 mm or better.
