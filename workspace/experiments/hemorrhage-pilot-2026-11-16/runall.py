"""Run every arm in jobs.txt, N at a time: python runall.py [N] (writes out/<label>.json, pilot.log)."""
import subprocess, sys, os
from concurrent.futures import ThreadPoolExecutor
D = os.path.dirname(os.path.abspath(__file__))
jobs = [l.split(None, 2) for l in open(f"{D}/jobs.txt") if l.strip()]
log = open(f"{D}/pilot.log", "w")
def go(j):
    l, k, w = j
    r = subprocess.run(["timeout", "1200", sys.executable, f"{D}/probe.py", l, k, w, f"{D}/out/{l}.json"], capture_output=True, text=True)
    log.write(r.stdout + (r.stderr[-800:] if r.returncode else "")); log.flush()
with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 2) as ex: list(ex.map(go, jobs))
log.write("ALLDONE\n")
