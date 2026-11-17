#!/bin/sh
# The hemorrhage arms at the study's 300 s (the first pass ran 600 s; 0.08 crashed at 391 s).
cd "$(dirname "$0")"
for a in dt-0.08 dt-0.04 dt-0.02; do python probe.py timestep-hemorrhage $a out/timestep-hemorrhage-$a.json 2>&1 | grep -v skipping; done
echo HEMDONE
