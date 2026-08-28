import json, subprocess, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import snapshot as S, diff as D, metrics as M

fails = []
def ck(name, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f"  (want {want!r})"))
    if not ok: fails.append(name)

# --- normalize() against a record shaped like the real API -------------------------------------
print("normalize() — real API shape")
raw = {"id":"meta-llama/Llama-3.1-8B-Instruct","author":"meta-llama","gated":"manual",
       "private":False,"downloads":41234567,"likes":3900,"sha":"abc",
       "tags":["transformers","safetensors","llama","license:llama3.1","text-generation"],
       "pipeline_tag":"text-generation","library_name":"transformers",
       "createdAt":"2024-07-18T00:00:00.000Z","lastModified":"2026-08-01T00:00:00.000Z",
       "siblings":[{"rfilename":"model-00001-of-00004.safetensors"},{"rfilename":"config.json"}]}
n = S.normalize(raw)
ck("license parsed from tags", n["license"], "llama3.1")
ck("llama3.1 is NOT permissive", n["license_permissive"], False)
ck("gated kept verbatim (not coerced)", n["gated"], "manual")
ck("no plural artifacts", n["artifacts_plural"], [])
ck("safetensors detected", n["weights"], ["safetensors"])

print("\nnormalize() — hardware-plural + nvidia-native")
raw2 = {"id":"nvidia/Qwen3.6-35B-A3B-NVFP4","tags":["license:apache-2.0"],
        "gated":False,"downloads":11700000,
        "siblings":[{"rfilename":"openvino/openvino_model.xml"},{"rfilename":"onnx/model.onnx"},
                    {"rfilename":"model-nvfp4.safetensors"},{"rfilename":"x.gguf"}]}
n2 = S.normalize(raw2)
ck("plural detected", n2["artifacts_plural"], ["gguf","onnx","openvino"])
ck("nvfp4 detected", n2["artifacts_cuda_native"], ["nvfp4"])
ck("apache-2.0 permissive", n2["license_permissive"], True)

print("\nnormalize() — undeclared license")
ck("no license tag -> None", S.normalize({"id":"x","tags":["pytorch"],"siblings":[]})["license"], None)
ck("permissive flag None, not False", S.normalize({"id":"x","tags":[],"siblings":[]})["license_permissive"], None)

# --- diff severity ------------------------------------------------------------------------------
print("\ndiff() — severity assignment")
old = {"captured_at":"2026-08-28T06:00:00+00:00","n":6,"models":[
  {"id":"a","license":"apache-2.0","gated":False,"artifacts_plural":["openvino","onnx"]},
  {"id":"b","license":"mit","gated":False,"artifacts_plural":[]},
  {"id":"c","license":"apache-2.0","gated":False,"artifacts_plural":["gguf"]},
  {"id":"d","license":"mit","gated":None,"artifacts_plural":[]},
  {"id":"e","license":"apache-2.0","gated":"auto","artifacts_plural":[]},
  {"id":"gone","license":"mit","gated":False,"artifacts_plural":[]}]}
new = {"captured_at":"2026-08-29T06:00:00+00:00","n":6,"models":[
  {"id":"a","license":"apache-2.0","gated":False,"artifacts_plural":["onnx"]},        # dropped openvino
  {"id":"b","license":None,"gated":False,"artifacts_plural":[]},                       # -> undeclared
  {"id":"c","license":"apache-2.0","gated":"manual","artifacts_plural":["gguf"]},      # became gated
  {"id":"d","license":"mit","gated":False,"artifacts_plural":[]},                      # None -> False
  {"id":"e","license":"apache-2.0","gated":"manual","artifacts_plural":[]},            # auto->manual
  {"id":"newbie","license":"mit","gated":False,"artifacts_plural":["coreml"]}]}
ev = {(e["model"], e["kind"]): e["sev"] for e in D.events(old, new)}
ck("permissive -> undeclared = CRITICAL", ev.get(("b","license_narrowed")), "CRITICAL")
ck("ungated -> gated = CRITICAL",         ev.get(("c","became_gated")), "CRITICAL")
ck("dropped openvino = HIGH",             ev.get(("a","dropped_plural_artifact")), "HIGH")
ck("auto -> manual = MEDIUM",             ev.get(("e","gating_mode_changed")), "MEDIUM")
ck("model left set = MEDIUM",             ev.get(("gone","left_set")), "MEDIUM")
ck("new model = LOW",                     ev.get(("newbie","entered_set")), "LOW")
ck("unknown->known gating fires NOTHING", ("d","became_gated") in ev, False)

# --- metrics ------------------------------------------------------------------------------------
print("\nmetrics() — coverage honesty")
m = M.compute(new)
ck("n", m["n"], 6)
ck("gated coverage 100%", m["gated_coverage"], 100.0)
ck("pct_gated = 2/6", m["pct_gated"], 33.33)
ck("undeclared = 1/6", m["pct_license_undeclared"], 16.67)
ck("hardware plural = 3/6", m["pct_hardware_plural"], 50.0)

partial = {"captured_at":"2026-08-29T06:00:00+00:00","models":[
  {"id":"a","gated":None,"license":"mit"},{"id":"b","gated":False,"license":"mit"}]}
mp = M.compute(partial)
ck("partial gated coverage flagged", mp["gated_coverage"], 50.0)
ck("pct_gated computed on KNOWN only", mp["pct_gated"], 0.0)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}"))
sys.exit(1 if fails else 0)
