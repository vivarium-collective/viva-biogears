"""Check a compose-api run's results file: ``check_results.py OUTPUT_DIR``.

The oracle is physiology, not a fixture. After a hemorrhage run (default 250 mL/min for the run's seconds), every
vital in the last emitted row is finite, blood volume is below its starting value, and the loss is positive.
(``total_blood_volume_lost_mL`` is NaN in row 0 before BioGears reports it, so only the last row is checked.)
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path


def check(output: Path) -> dict:
    files = sorted(glob.glob(str(output / "results_*.pber")))
    if len(files) != 1:
        raise SystemExit(f"expected one results_*.pber in {output}, found {files}")
    results = json.loads(Path(files[0]).read_text())
    rows = results["emitter"]
    first, last = rows[0], rows[-1]
    bad = {k: v for k, v in last.items() if isinstance(v, float) and not math.isfinite(v)}
    if bad:
        raise SystemExit(f"non-finite vitals in the last row: {bad}")
    if not last["time"] > first["time"]:
        raise SystemExit(f"the run did not advance: {first['time']} -> {last['time']}")
    if not last["blood_volume_mL"] < first["blood_volume_mL"]:
        raise SystemExit(f"a hemorrhage did not lower blood volume: {first['blood_volume_mL']} -> {last['blood_volume_mL']}")
    if not last["total_blood_volume_lost_mL"] > 0:
        raise SystemExit(f"no blood loss reported: {last['total_blood_volume_lost_mL']}")
    return {"rows": len(rows), "t_end": last["time"], "HR": last["heart_rate_bpm"], "MAP": last["mean_arterial_pressure_mmHg"],
            "lost_mL": last["total_blood_volume_lost_mL"]}


if __name__ == "__main__":
    print("results OK", check(Path(sys.argv[1])))
