#!/bin/sh
# Run every arm of both timestep studies, one at a time (python probe.py ...).
cd "$(dirname "$0")"
for s in timestep-hemorrhage timestep-sepsis; do for a in dt-0.08 dt-0.04 dt-0.02; do
  python probe.py $s $a out/$s-$a.json 2>&1 | grep -v skipping
done; done
echo ALLDONE
