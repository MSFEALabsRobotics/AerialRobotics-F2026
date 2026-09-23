# Building the whole archive on your own machine

Put `apc_prop.py` and your PE0 files in the same folder, then either
double-click `run_all.bat`, or run this from PowerShell in that folder:

```powershell
python apc_prop.py --check
python apc_prop.py . ALL_PROPS --split --step-ruled --resume
```

That writes one folder per propeller under `ALL_PROPS`, each holding the
geometry file it was built from plus the STL, OBJ, ruled STEP and HTML viewer.

Expect 30 to 60 minutes for all 450 and about 5.6 GB on disk. `--resume` makes
it safe to stop and restart: it skips anything already written.

## Before you start

`python apc_prop.py --check` should print:

```
  solid fusion : yes (numpy + manifold3d)
  STEP quality : NURBS B-rep (cadquery)
```

If either line says otherwise, `python -m pip install numpy manifold3d cadquery`
and check again. Without cadquery every STEP is a faceted approximation, which
is no use in SolidWorks, and the run is wasted.

## Checking it went right

`ALL_PROPS\summary.csv` lists what was built. Nothing should be reported as
skipped or failed: all 450 files build, 432 as a hub with blades and 18 as a
single blade, those being the folding models whose files carry no hub.

Compare against `MANIFEST.csv`, which is the manifest from my run here. Volumes
should match it closely. Median volume against the figure each file quotes is
-7.3%, and the models are always light, never heavy, for the reason set out in
`READ_ME_FIRST.txt`.
