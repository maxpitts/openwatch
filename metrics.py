#!/usr/bin/env python3
"""metrics.py — reduce a snapshot to the few numbers the site actually plots.

This exists so the website never has to download the ledger. A top-5,000 snapshot is tens of MB
and grows a new one every day; metrics.json is a few KB and stays that size roughly forever,
because it's one row per day, not one row per model. The page reads the time series. The archive
stays in git for anyone who wants to audit it.

    python3 metrics.py --snapshot data/2026-08-28.json --series data/metrics.json
"""
from __future__ import annotations

import argparse, json, os, sys
from collections import Counter


def pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def compute(snap: dict) -> dict:
    ms = snap.get("models") or []
    n = len(ms)
    if not n:
        raise SystemExit("snapshot contains no models")

    declared = [m for m in ms if m.get("license")]
    # gated is False | "auto" | "manual". Anything truthy counts as gated; None means the field was
    # missing from the record, which is NOT the same as ungated and must not be silently folded in.
    gated_known = [m for m in ms if m.get("gated") is not None]
    gated = [m for m in gated_known if m.get("gated") not in (False, "false", "")]

    plural_any = [m for m in ms if m.get("artifacts_plural")]
    cuda_any = [m for m in ms if m.get("artifacts_cuda_native")]

    fam = Counter()
    for m in ms:
        for k in m.get("artifacts_plural") or []:
            fam[k] += 1
        for k in m.get("artifacts_cuda_native") or []:
            fam[k] += 1

    return {
        "date": (snap.get("captured_at") or "")[:10],
        "captured_at": snap.get("captured_at"),
        "n": n,
        "pct_permissive": pct(sum(1 for m in declared if m.get("license_permissive")), n),
        "pct_license_undeclared": pct(n - len(declared), n),
        "pct_gated": pct(len(gated), len(gated_known)),
        "gated_coverage": pct(len(gated_known), n),   # if this isn't ~100, pct_gated is unreliable
        # THE headline number: share of top models that ship anything runnable off Nvidia silicon.
        "pct_hardware_plural": pct(len(plural_any), n),
        "pct_cuda_native": pct(len(cuda_any), n),
        "artifact_counts": dict(sorted(fam.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--series", required=True)
    a = ap.parse_args()
    row = compute(json.load(open(a.snapshot)))

    series = []
    if os.path.exists(a.series):
        try:
            series = json.load(open(a.series))
        except Exception:
            series = []
    # one row per date; a same-day re-run replaces rather than duplicates
    series = [r for r in series if r.get("date") != row["date"]] + [row]
    series.sort(key=lambda r: r.get("date") or "")
    with open(a.series, "w") as f:
        json.dump(series, f, indent=1)

    print(f"metrics {row['date']}: n={row['n']}  permissive={row['pct_permissive']}%  "
          f"undeclared={row['pct_license_undeclared']}%  gated={row['pct_gated']}% "
          f"(coverage {row['gated_coverage']}%)  hardware-plural={row['pct_hardware_plural']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
