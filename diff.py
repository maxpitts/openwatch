#!/usr/bin/env python3
"""diff.py — turn two snapshots into a severity-ranked list of change events.

The thesis is that erosion is gradual and quiet. Nobody announces "we narrowed a license" or
"we stopped shipping the Intel build." Those only become visible if something diffs the Hub against
itself and ranks what it finds, so the signal isn't buried under thousands of download-count wiggles.

SEVERITY, and why each tier is where it is:

  CRITICAL — the model got less usable to someone who already depended on it:
             a permissive license going restrictive or undeclared, or ungated going gated.
  HIGH     — hardware plurality shrank: a model dropped its OpenVINO / ONNX / CoreML / GGUF build.
             This is the specific failure mode people fear from the acquisition, so it gets its own
             tier rather than being lumped in with generic metadata churn.
  MEDIUM   — a license changed but not in an obviously worse direction; gating mode changed;
             a model that was in the ranked set is no longer returned by the API.
  LOW      — a model entered the set; artifacts were ADDED. Recorded for completeness, not alarm.

    python3 diff.py --old data/2026-08-28.json --new data/2026-08-29.json --out reports/2026-08-29.md
"""
from __future__ import annotations

import argparse, json, sys

PERMISSIVE = {"apache-2.0", "mit", "bsd", "bsd-3-clause", "bsd-2-clause", "cc0-1.0",
              "cc-by-4.0", "unlicense", "isc", "openrail", "bigscience-openrail-m"}
RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def is_gated(v) -> bool:
    return v not in (None, False, "false", "")


def events(old: dict, new: dict) -> list[dict]:
    o = {m["id"]: m for m in old.get("models", []) if m.get("id")}
    n = {m["id"]: m for m in new.get("models", []) if m.get("id")}
    out: list[dict] = []

    for mid, b in n.items():
        a = o.get(mid)
        if a is None:
            out.append({"sev": "LOW", "kind": "entered_set", "model": mid,
                        "detail": f"new in ranked set (downloads {b.get('downloads'):,})"
                        if isinstance(b.get("downloads"), int) else "new in ranked set"})
            continue

        la, lb = a.get("license"), b.get("license")
        if la != lb:
            was_perm = la in PERMISSIVE if la else False
            now_perm = lb in PERMISSIVE if lb else False
            if was_perm and not now_perm:
                out.append({"sev": "CRITICAL", "kind": "license_narrowed", "model": mid,
                            "detail": f"{la or 'none'} -> {lb or 'UNDECLARED'}"})
            else:
                out.append({"sev": "MEDIUM", "kind": "license_changed", "model": mid,
                            "detail": f"{la or 'none'} -> {lb or 'none'}"})

        ga, gb = a.get("gated"), b.get("gated")
        # Only compare when BOTH sides actually recorded the field. A missing value is unknown,
        # not "ungated" — treating it otherwise is how you manufacture a fake CRITICAL.
        if ga is not None and gb is not None and ga != gb:
            if not is_gated(ga) and is_gated(gb):
                out.append({"sev": "CRITICAL", "kind": "became_gated", "model": mid,
                            "detail": f"ungated -> gated ({gb})"})
            elif is_gated(ga) and not is_gated(gb):
                out.append({"sev": "LOW", "kind": "ungated", "model": mid, "detail": f"{ga} -> open"})
            else:
                out.append({"sev": "MEDIUM", "kind": "gating_mode_changed", "model": mid,
                            "detail": f"{ga} -> {gb}"})

        pa, pb = set(a.get("artifacts_plural") or []), set(b.get("artifacts_plural") or [])
        for lost in sorted(pa - pb):
            out.append({"sev": "HIGH", "kind": "dropped_plural_artifact", "model": mid,
                        "detail": f"no longer ships {lost}"})
        for got in sorted(pb - pa):
            out.append({"sev": "LOW", "kind": "added_plural_artifact", "model": mid,
                        "detail": f"now ships {got}"})

    for mid in o.keys() - n.keys():
        out.append({"sev": "MEDIUM", "kind": "left_set", "model": mid,
                    "detail": "no longer returned in the ranked set (fell in rank, or removed)"})

    out.sort(key=lambda e: (RANK[e["sev"]], e["kind"], e["model"]))
    return out


def report(old: dict, new: dict, evs: list[dict]) -> str:
    counts = {s: sum(1 for e in evs if e["sev"] == s) for s in RANK}
    L = [f"# Open Model Watch — {(new.get('captured_at') or '')[:10]}", "",
         f"Comparing `{(old.get('captured_at') or '?')[:10]}` -> `{(new.get('captured_at') or '?')[:10]}`  ",
         f"{old.get('n', 0):,} -> {new.get('n', 0):,} models in the ranked set", "",
         "| severity | events |", "|---|---|"]
    L += [f"| {s} | {counts[s]} |" for s in RANK]
    L.append("")
    if not evs:
        L += ["No changes detected.", ""]
    for s in RANK:
        rows = [e for e in evs if e["sev"] == s]
        if not rows:
            continue
        L += [f"## {s} ({len(rows)})", ""]
        # LOW is mostly rank churn and would drown the file; the full set is always in the snapshots.
        show = rows if s != "LOW" else rows[:40]
        L += [f"- **{e['model']}** — {e['kind']}: {e['detail']}" for e in show]
        if len(rows) > len(show):
            L.append(f"- _...and {len(rows) - len(show)} more (see snapshots)_")
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--out")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    old, new = json.load(open(a.old)), json.load(open(a.new))
    evs = events(old, new)
    md = report(old, new, evs)
    if a.out:
        open(a.out, "w").write(md)
    if a.json_out:
        json.dump(evs, open(a.json_out, "w"), indent=1)
    crit = sum(1 for e in evs if e["sev"] in ("CRITICAL", "HIGH"))
    print(md if not a.out else f"wrote {a.out} ({len(evs)} events, {crit} critical/high)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
