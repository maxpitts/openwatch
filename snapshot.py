#!/usr/bin/env python3
"""snapshot.py — take one metadata-only reading of the Hugging Face Hub.

WHY THIS SHAPE
--------------
This file is the ledger. Everything downstream (metrics, diffs, the site) is derived and can be
regenerated; a snapshot cannot, because you cannot go back and ask what a model's license said
last March. So the rules here are deliberately boring:

  1. NO MODEL IS INVOLVED IN THE EXTRACTION PATH. Raw JSON in, dict out, stdlib only. An earlier
     prototype ran the sample through an LLM to "tidy" it and silently reported 0% gated across
     the board, which is false — meta-llama/Llama-3.1-8B-Instruct is gated upstream. A watchdog
     whose numbers can be wrong in an unfalsifiable way is worse than no watchdog.
  2. METADATA ONLY. No weights, ever. That keeps a full run in the tens of MB instead of petabytes,
     which is the entire reason this is fundable and the mirror projects aren't.
  3. FAIL LOUD, WRITE NOTHING. A partial snapshot that looks complete would poison every future
     diff. If pagination breaks we raise; the Action stops before its commit step.

WHAT WE MEASURE, AND WHY IT'S NOT A VIBE
----------------------------------------
The concern after Nvidia's reported $12.9B acquisition isn't that models get deleted — it's that
neutrality erodes quietly. That is measurable, because every model's record includes its full file
manifest. A repo shipping openvino/ or coreml/ or .gguf alongside safetensors is hardware-plural;
one shipping only Nvidia-native formats is not. So "did the CUDA path become the only path" turns
into a percentage with a date on it.

USAGE
    python3 snapshot.py --top 5000 --out data/2026-08-28.json
"""
from __future__ import annotations

import argparse, datetime as dt, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

API = "https://huggingface.co/api/models"
UA = "openwatch/1.0 (+https://github.com/openwatch) python-urllib"

# Artifact families. "cuda_native" are formats that only pay off on Nvidia silicon; "plural" ship
# for someone else's accelerator. A model can be in both — that's the healthy case, and the whole
# point is to watch whether the plural column thins out over time.
PLURAL = {
    "openvino": (r"(^|/)openvino/", r"openvino_model\.(xml|bin)$"),      # Intel
    "onnx":     (r"(^|/)onnx/", r"\.onnx$"),                              # vendor-neutral runtime
    "coreml":   (r"(^|/)coreml/", r"\.mlpackage(/|$)", r"\.mlmodelc(/|$)"),  # Apple
    "gguf":     (r"\.gguf$",),                                            # llama.cpp / CPU + AMD
    "tflite":   (r"\.tflite$",),                                          # edge
    "rknn":     (r"\.rknn$",),                                            # Rockchip NPU
}
CUDA_NATIVE = {
    "tensorrt": (r"\.engine$", r"(^|/)tensorrt", r"\.plan$"),
    "nvfp4":    (r"nvfp4", ),          # Nvidia Model Optimizer FP4
    "trtllm":   (r"trt[-_]?llm", ),
}
NEUTRAL_WEIGHTS = {"safetensors": (r"\.safetensors$",), "pytorch": (r"\.(bin|pth|pt)$",)}

PERMISSIVE = {"apache-2.0", "mit", "bsd", "bsd-3-clause", "bsd-2-clause", "cc0-1.0",
              "cc-by-4.0", "unlicense", "isc", "openrail", "bigscience-openrail-m"}


def _match(names: list[str], pats) -> bool:
    for p in pats:
        rx = re.compile(p, re.I)
        for n in names:
            if rx.search(n):
                return True
    return False


def license_of(tags: list[str]) -> str | None:
    """HF has no top-level license field — it's a `license:xxx` tag. Absent means UNDECLARED,
    which is its own risk category (nothing stops it being narrowed later), not 'probably fine'."""
    for t in tags or []:
        if isinstance(t, str) and t.startswith("license:"):
            return t.split(":", 1)[1].strip().lower() or None
    return None


def normalize(m: dict) -> dict:
    files = [s.get("rfilename", "") for s in (m.get("siblings") or []) if isinstance(s, dict)]
    tags = [t for t in (m.get("tags") or []) if isinstance(t, str)]
    lic = license_of(tags)
    plural = sorted(k for k, p in PLURAL.items() if _match(files, p))
    cuda = sorted(k for k, p in CUDA_NATIVE.items() if _match(files, p))
    return {
        "id": m.get("id") or m.get("modelId"),
        "author": m.get("author"),
        "downloads": m.get("downloads"),
        "likes": m.get("likes"),
        # gated is False | "auto" | "manual" upstream. Keep it verbatim — never coerce to bool.
        "gated": m.get("gated"),
        "private": m.get("private"),
        "license": lic,
        "license_permissive": (lic in PERMISSIVE) if lic else None,
        "pipeline_tag": m.get("pipeline_tag"),
        "library_name": m.get("library_name"),
        "created_at": m.get("createdAt"),
        "last_modified": m.get("lastModified"),
        "sha": m.get("sha"),
        "n_files": len(files),
        "artifacts_plural": plural,          # runs on non-Nvidia silicon
        "artifacts_cuda_native": cuda,       # Nvidia-only formats
        "weights": sorted(k for k, p in NEUTRAL_WEIGHTS.items() if _match(files, p)),
    }


def fetch(url: str, tries: int = 4) -> tuple[list, str | None]:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            tok = os.environ.get("HF_TOKEN")          # optional: only raises the rate limit
            if tok:
                req.add_header("Authorization", "Bearer " + tok)
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.load(r)
                nxt = None
                link = r.headers.get("Link") or ""
                mm = re.search(r'<([^>]+)>;\s*rel="next"', link)
                if mm:
                    nxt = mm.group(1)
                return body, nxt
        except Exception as e:                          # noqa: BLE001 — retry anything transient
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"GET failed after {tries} tries: {url} -> {last}")


def capture(top: int, page: int = 100) -> dict:
    seen, rows = set(), []
    url = f"{API}?{urllib.parse.urlencode({'sort':'downloads','direction':-1,'limit':page,'full':'true'})}"
    pages = 0
    while url and len(rows) < top:
        batch, url = fetch(url)
        if not batch:
            break
        pages += 1
        for m in batch:
            mid = m.get("id") or m.get("modelId")
            if not mid or mid in seen:      # cursor pages can overlap; de-dupe by id, not position
                continue
            seen.add(mid)
            rows.append(normalize(m))
            if len(rows) >= top:
                break
        print(f"  page {pages:>3}  total {len(rows):>6}", file=sys.stderr)
    if len(rows) < top:
        print(f"note: hub returned {len(rows)} of {top} requested", file=sys.stderr)
    return {
        "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": API,
        "rank_by": "downloads",
        "n": len(rows),
        "requested": top,
        "schema": 1,
        "models": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    snap = capture(a.top)
    if not snap["models"]:
        print("REFUSING TO WRITE: zero models captured", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(snap, f, indent=1, sort_keys=True)
    print(f"wrote {a.out}  ({snap['n']} models, {os.path.getsize(a.out)/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
