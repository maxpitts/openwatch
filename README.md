# Open Model Watch

A daily, append-only record of how open the open-model ecosystem actually is.

On 27 August 2026, Nvidia was reported to have agreed to acquire Hugging Face for $12.9B. The
concern that followed was not that models get deleted — nobody expects that. It's that neutrality
erodes quietly: licenses narrow, weights go gated, and the builds that run on AMD, Intel or Apple
silicon stop being published, one repo at a time, with no announcement. A competing accelerator
doesn't have to be banned to become less appealing.

Gradual, unannounced change is invisible unless something takes a picture every day and diffs it.
That's all this is.

## What it measures

Every model record on the Hub includes its full file manifest, which makes hardware plurality
**countable rather than arguable**. A repo shipping `openvino/`, `onnx/`, `coreml/` or `.gguf`
alongside its safetensors runs on someone else's silicon. One shipping only Nvidia-native formats
(`.engine`, NVFP4, TRT-LLM) does not. So "did the CUDA path become the only path" becomes a
percentage with a date attached.

Tracked daily across the top N models by downloads:

| metric | why it's here |
|---|---|
| `pct_hardware_plural` | the headline: share shipping anything runnable off Nvidia silicon |
| `pct_cuda_native` | the other side of the same trend |
| `pct_permissive` | Apache-2.0 / MIT / BSD and friends |
| `pct_license_undeclared` | the silent-narrowing risk pool — nothing stops these being restricted later |
| `pct_gated` | access-controlled weights |
| `gated_coverage` | **read this before citing `pct_gated`** — if it isn't ~100%, the field was missing upstream |

## Why the git history is the point

The repo is the ledger; anything else is a reader over it. Git history is append-only and public,
so nobody — including whoever runs this — can quietly revise what a model's license said last March.
That property is what makes the record citable, and it's why the snapshots must be committed by the
Action from a public repo rather than living in a database someone controls.

A dashboard backed by a private table proves nothing. `git log -- data/` proves everything.

## Design rules

1. **No model in the extraction path.** Raw JSON in, dict out, stdlib only. An early prototype ran
   the sample through an LLM to tidy it and silently reported 0% gated — which is false;
   `meta-llama/Llama-3.1-8B-Instruct` is gated upstream. A watchdog that can be wrong in an
   unfalsifiable way is worse than none.
2. **Metadata only, never weights.** Keeps a full run in tens of MB. Bandwidth is why every
   ownerless mirror ends up torrent-based; measuring metadata sidesteps that entirely.
3. **Fail closed.** A partial capture would poison every future diff, so the scraper raises and the
   Action stops before its commit step.
4. **Missing ≠ false.** `gated: None` means the field wasn't recorded, not that the model is open.
   Unknown values never generate events and never enter percentages.

## Files

```
snapshot.py   one metadata reading of the Hub -> data/YYYY-MM-DD.json   (the ledger)
metrics.py    snapshot -> one row appended to data/metrics.json         (a few KB, forever)
diff.py       two snapshots -> severity-ranked events + reports/*.md
.github/workflows/daily.yml   runs all three at 06:17 UTC and commits
tests/test_all.py             fixtures for every event type and edge case
```

Severity: **CRITICAL** = permissive license narrowed, or ungated → gated. **HIGH** = a
hardware-plural build was dropped. **MEDIUM** = other license/gating change, or a model leaving the
ranked set. **LOW** = additions and new entrants.

## License

Code MIT. Data CC0 — fork it, mirror it, and if this repo ever goes quiet or starts lying, the
history is right there to check it against.
