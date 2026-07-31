"""
logic/lora_decay_series.py
---------------------------
Renders one fixed prompt at a fixed seed across a varying LoRA, in order,
and assembles the result forward and reversed.

Two modes:

  --mode strength     one trained LoRA, strength swept 0 -> 1.5+.
                      A continuous dissolution, and only one training run.
                      Strength IS a dial, which puts it in the same family
                      as the pipeline's other epistemic controls
                      (sketch_alpha: designer over data; data_alpha: measured
                      noise over painted intent). Past ~1.2 the LoRA
                      overwhelms the base model and output degrades into
                      exactly the incoherent ghosting the thesis paper
                      describes -- that is the interesting end of the sweep,
                      not a mistake to avoid.

  --mode checkpoints  every saved checkpoint of a training run, in step
                      order. The true learning trajectory, but it needs a
                      trainer configured to save intermediates.

WHY: a LoRA passes through exactly the states the paper describes -- "blurry,
incoherent, and ghostlike... almost recognizable instances appear, but are
not easily remembered due to their uncanniness." Played forward the series
is a model acquiring a place. Played backward it is that place dissolving
out of legibility: the trajectory of The Caretaker's Everywhere at the End
of Time, run on the site's own archive.

THE ONE CONTROL THAT MATTERS: seed, prompt, sampler, scheduler, steps, cfg
and resolution are identical for every frame. If the seed moves between
frames you are watching noise change rather than the model change, and the
series demonstrates nothing.

BRING YOUR OWN WORKFLOW: --workflow accepts any ComfyUI API-format graph, so
an SDXL pipeline you have already tuned can drive this instead of the bundled
template. Node ids are auto-detected by class_type (and positive/negative
prompts by following the sampler's own links), so no ids need to be
hand-wired unless a graph is ambiguous -- e.g. an SDXL base+refiner workflow
with two KSamplers, where --node-sampler picks the one to drive.

Export from ComfyUI with **Save (API Format)**, not plain Save -- the plain
UI format is a different schema and POST /prompt rejects it.

Run:
    .venv/Scripts/python.exe logic/lora_decay_series.py --list-models
    .venv/Scripts/python.exe logic/lora_decay_series.py --inspect \\
        --workflow logic/workflows/my_sdxl.json
    .venv/Scripts/python.exe logic/lora_decay_series.py --mode strength \\
        --lora pershing_collapsed.safetensors --base sd_xl_base_1.0.safetensors \\
        --prompt "pershingsq, aerial view" --dry-run
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from logic.comfy_client import (  # noqa: E402
    COMFY_URL, ping, queue_workflow, poll_for_output, load_workflow, patch_workflow)

DEFAULT_WORKFLOW = os.path.join(BASE_DIR, "logic", "workflows", "lora_decay.json")
OUTPUT_ROOT = os.path.join(BASE_DIR, "outputs", "lora_decay")

# class_type -> role. Alternatives are listed because real workflows vary:
# SDXL graphs often use KSamplerAdvanced, and LoRA-only loaders appear in
# graphs that drive CLIP separately.
SAMPLER_CLASSES = ("KSampler", "KSamplerAdvanced")
LORA_CLASSES = ("LoraLoader", "LoraLoaderModelOnly")
CKPT_CLASSES = ("CheckpointLoaderSimple", "CheckpointLoader")
LATENT_CLASSES = ("EmptyLatentImage", "EmptySD3LatentImage")
SAVE_CLASSES = ("SaveImage",)
LOADIMAGE_CLASSES = ("LoadImage",)


def upload_image(path):
    """POST an image to ComfyUI's input/ so a LoadImage node can reference it.

    Necessary because LoadImage takes a FILENAME relative to ComfyUI's own
    input directory, not an arbitrary path -- and ComfyUI may not even be on
    the same drive as this repo (it is on D: here while comfy_client's old
    default pointed at C:). Uploading sidesteps the filesystem entirely, so
    this works even if ComfyUI runs on another machine.

    Returns the name ComfyUI stored it under, which may differ from the name
    sent if a file of that name already existed.
    """
    name = os.path.basename(path)
    with open(path, "rb") as f:
        payload = f.read()
    boundary = "----MemoryMachineBoundary"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
        b"Content-Type: application/octet-stream\r\n\r\n",
        payload, b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{COMFY_URL}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    stored = out.get("name", name)
    sub = out.get("subfolder") or ""
    return f"{sub}/{stored}" if sub else stored


# Set during --dry-run: the registry is expected to be unreachable then
# (that is the point of a dry run), so its connection error is noise rather
# than a fault worth reporting.
QUIET_REGISTRY = False


def object_info(category=None):
    """GET /object_info -- ComfyUI's registry of what is actually installed."""
    url = f"{COMFY_URL}/object_info" + (f"/{category}" if category else "")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        if not QUIET_REGISTRY:
            print(f"[decay] could not read {url}: {e}")
        return None


def available(node_class, input_name):
    info = object_info(node_class)
    if not info:
        return []
    try:
        spec = info[node_class]["input"]["required"][input_name]
        return list(spec[0]) if isinstance(spec[0], list) else []
    except (KeyError, IndexError, TypeError):
        return []


def strip_comments(workflow):
    """Drop documentation keys. ComfyUI would reject them as node ids with
    an unknown class_type."""
    return {k: v for k, v in workflow.items()
            if not k.startswith("_") and isinstance(v, dict) and "class_type" in v}


def _find(workflow, classes):
    return [nid for nid, n in workflow.items() if n.get("class_type") in classes]


def autodetect_nodes(workflow, overrides=None):
    """Map roles -> node ids for an arbitrary API-format workflow.

    Positive and negative prompts are resolved by following the sampler's
    own `positive`/`negative` links rather than by guessing between two
    identical CLIPTextEncode nodes -- the link is ground truth, the node
    order is not.
    """
    overrides = {k: v for k, v in (overrides or {}).items() if v}
    roles = {}

    def pick(role, classes, required=True):
        if role in overrides:
            roles[role] = overrides[role]
            return
        found = _find(workflow, classes)
        if len(found) == 1:
            roles[role] = found[0]
        elif len(found) > 1:
            raise SystemExit(
                f"ambiguous: {len(found)} {'/'.join(classes)} nodes ({', '.join(sorted(found))}).\n"
                f"Pass --node-{role} <id> to choose. Run --inspect to see the graph.")
        elif required:
            raise SystemExit(
                f"workflow has no {'/'.join(classes)} node.\n"
                + ("Add a LoraLoader between your checkpoint and the sampler/CLIP.\n"
                   if role == "lora" else ""))

    pick("sampler", SAMPLER_CLASSES)
    pick("lora", LORA_CLASSES)
    pick("checkpoint", CKPT_CLASSES, required=False)
    pick("latent", LATENT_CLASSES, required=False)
    pick("save", SAVE_CLASSES, required=False)
    pick("loadimage", LOADIMAGE_CLASSES, required=False)

    sampler = workflow[roles["sampler"]]["inputs"]
    for role, key in (("positive", "positive"), ("negative", "negative")):
        if role in overrides:
            roles[role] = overrides[role]
        else:
            link = sampler.get(key)
            if isinstance(link, list) and link:
                roles[role] = link[0]
    return roles


def seed_key(workflow, sampler_id):
    """KSampler calls it `seed`; KSamplerAdvanced calls it `noise_seed`.
    Patching the wrong one silently leaves the seed at its baked-in value --
    which looks like it worked, and quietly destroys the experiment's only
    control."""
    return "noise_seed" if workflow[sampler_id]["class_type"] == "KSamplerAdvanced" else "seed"


def inspect(workflow):
    print(f"{len(workflow)} nodes:")
    for nid in sorted(workflow, key=lambda x: (len(x), x)):
        n = workflow[nid]
        wid = {k: v for k, v in n["inputs"].items() if not isinstance(v, list)}
        s = json.dumps(wid)[:90]
        print(f"  {nid:>4}  {n['class_type']:<28} {s}")
    try:
        roles = autodetect_nodes(workflow)
        print("\ndetected roles:")
        for r, nid in sorted(roles.items()):
            print(f"  {r:<11} -> node {nid}  ({workflow[nid]['class_type']})")
        print(f"  seed field  -> {seed_key(workflow, roles['sampler'])}")
    except SystemExit as e:
        print(f"\nautodetect: {e}")


def _step_of(name):
    nums = re.findall(r"(\d+)", os.path.basename(name))
    return int(nums[-1]) if nums else -1


def discover_checkpoints(pattern):
    loras = available("LoraLoader", "lora_name")
    hits = [l for l in loras if pattern.lower() in l.lower()]
    return sorted(hits, key=_step_of)


def build_jobs_strength(lora, values):
    return [{"label": f"strength_{v:0.2f}".replace(".", "p"), "lora": lora, "strength": v}
            for v in values]


def build_jobs_denoise(lora, strength, values):
    """Sweep img2img denoise at fixed LoRA strength.

    Asks how much of a viewport render survives contact with the site's
    remembered appearance: near 0 the proposal's geometry is intact and only
    surface is recalled, near 1 the memory has overwritten it completely.
    """
    return [{"label": f"denoise_{v:0.2f}".replace(".", "p"), "lora": lora,
             "strength": strength, "denoise": v} for v in values]


def build_jobs_checkpoints(checkpoints, include_baseline):
    jobs = []
    if include_baseline:
        jobs.append({"label": "step0000_baseline", "lora": checkpoints[0], "strength": 0.0})
    for ck in checkpoints:
        jobs.append({"label": f"step{_step_of(ck):04d}", "lora": ck, "strength": 1.0})
    return jobs


def render_series(jobs, workflow, roles, opts, run_name, dry_run=False):
    run_dir = os.path.join(OUTPUT_ROOT, run_name)
    fwd_dir = os.path.join(run_dir, "forward")
    os.makedirs(fwd_dir, exist_ok=True)

    print(f"\n{len(jobs)} frames -> {fwd_dir}")
    for j in jobs:
        extra = f" denoise={j['denoise']}" if "denoise" in j else ""
        print(f"   {j['label']:<22} strength={j['strength']:<5}{extra}  {j['lora']}")
    if dry_run:
        print("\n--dry-run: nothing queued")
        return None

    # img2img: push the init image into ComfyUI's input/ once, up front --
    # it is identical for every frame, so re-uploading per frame would just
    # be wasted transfer.
    init_name = None
    if opts.get("init_image"):
        if not roles.get("loadimage"):
            raise SystemExit("--init-image needs a LoadImage node in the workflow "
                             "(use logic/workflows/lora_img2img.json, or add one)")
        init_name = upload_image(opts["init_image"])
        print(f"   uploaded init image as {init_name!r}")

    skey = seed_key(workflow, roles["sampler"])
    manifest = []
    for i, j in enumerate(jobs):
        patches = {
            roles["lora"]: {"lora_name": j["lora"], "strength_model": j["strength"]},
            roles["sampler"]: {skey: opts["seed"]},
        }
        # LoraLoaderModelOnly has no CLIP strength input; patching a key a
        # node does not declare would be silently ignored by ComfyUI, so
        # only send it where it exists.
        if "strength_clip" in workflow[roles["lora"]]["inputs"]:
            patches[roles["lora"]]["strength_clip"] = j["strength"]
        for key in ("steps", "cfg", "sampler_name", "scheduler"):
            if opts.get(key) is not None and key in workflow[roles["sampler"]]["inputs"]:
                patches[roles["sampler"]][key] = opts[key]
        # Per-frame denoise (sweep) takes precedence over a fixed --denoise.
        denoise = j.get("denoise", opts.get("denoise"))
        if denoise is not None and "denoise" in workflow[roles["sampler"]]["inputs"]:
            patches[roles["sampler"]]["denoise"] = denoise
        if init_name:
            patches[roles["loadimage"]] = {"image": init_name}
        if opts.get("prompt") and roles.get("positive"):
            patches[roles["positive"]] = {"text": opts["prompt"]}
        if opts.get("negative") is not None and roles.get("negative"):
            patches[roles["negative"]] = {"text": opts["negative"]}
        if opts.get("base") and roles.get("checkpoint"):
            patches[roles["checkpoint"]] = {"ckpt_name": opts["base"]}
        if roles.get("latent") and opts.get("width"):
            patches[roles["latent"]] = {"width": opts["width"], "height": opts["height"]}
        if roles.get("save"):
            patches[roles["save"]] = {"filename_prefix": f"lora_decay/{run_name}_{j['label']}"}

        pid = queue_workflow(patch_workflow(workflow, patches))
        if not pid:
            print(f"   ! queue failed for {j['label']}")
            continue
        out = poll_for_output(pid, expected_ext=".png")
        if not out or not os.path.exists(out):
            print(f"   ! no output for {j['label']}")
            continue
        dst = os.path.join(fwd_dir, f"{i:03d}_{j['label']}.png")
        shutil.copy2(out, dst)
        manifest.append({"index": i, "label": j["label"], "lora": j["lora"],
                         "strength": j["strength"], "denoise": denoise,
                         "file": os.path.basename(dst)})
        print(f"   [{i + 1}/{len(jobs)}] {os.path.basename(dst)}")

    with open(os.path.join(run_dir, "series.json"), "w", encoding="utf8") as f:
        json.dump({"run": run_name, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   **opts, "roles": roles, "frames": manifest}, f, indent=2)
    return run_dir


def assemble(run_dir, frame_ms=450, hold_ms=1600):
    """forward.gif and reverse.gif from the rendered frames. PIL only -- no
    ffmpeg dependency. The final frame of each direction is held longer so
    the series resolves instead of snapping back on loop."""
    try:
        from PIL import Image
    except ImportError:
        print("[decay] Pillow unavailable -- frames written, GIFs skipped")
        return
    fwd = os.path.join(run_dir, "forward")
    names = sorted(f for f in os.listdir(fwd) if f.endswith(".png"))
    if len(names) < 2:
        print("[decay] need >= 2 frames to assemble")
        return
    frames = [Image.open(os.path.join(fwd, n)).convert("RGB") for n in names]
    for label, seq in (("forward", frames), ("reverse", list(reversed(frames)))):
        durations = [frame_ms] * len(seq)
        durations[-1] = hold_ms
        path = os.path.join(run_dir, f"{label}.gif")
        seq[0].save(path, save_all=True, append_images=seq[1:],
                    duration=durations, loop=0, optimize=True)
        print(f"   {label}.gif ({len(seq)} frames) -> {path}")
    print("\nreverse.gif is the artifact: the site dissolving out of legibility.")


def parse_sweep(spec):
    """'0,0.25,0.5' -> explicit list; '0:1.5:7' -> 7 values from 0 to 1.5."""
    if ":" in spec:
        lo, hi, n = spec.split(":")
        lo, hi, n = float(lo), float(hi), int(n)
        if n < 2:
            return [lo]
        return [round(lo + (hi - lo) * i / (n - 1), 4) for i in range(n)]
    return [float(v) for v in spec.split(",") if v.strip()]


def main():
    ap = argparse.ArgumentParser(description="Render a LoRA decay / strength series.")
    ap.add_argument("--mode", choices=("strength", "checkpoints", "denoise"), default="strength")
    ap.add_argument("--init-image", default=None,
                    help="img2img source, e.g. a viewport screenshot (needs a LoadImage node)")
    ap.add_argument("--denoise", type=float, default=None,
                    help="fixed img2img denoise; --mode denoise sweeps it instead")
    ap.add_argument("--workflow", default=DEFAULT_WORKFLOW,
                    help="ComfyUI API-format workflow (default: bundled template)")
    ap.add_argument("--inspect", action="store_true", help="print graph + detected roles, exit")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--lora", help="[strength] the trained LoRA filename")
    ap.add_argument("--sweep", default="0:1.5:11",
                    help="'lo:hi:count' or explicit '0,0.5,1.0'; sweeps strength "
                         "or denoise depending on --mode")
    ap.add_argument("--strength", type=float, default=1.0,
                    help="[denoise mode] fixed LoRA strength while denoise sweeps")
    ap.add_argument("--checkpoints", help="[checkpoints] substring matching saved checkpoints")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument("--base", default=None, help="base checkpoint filename")
    ap.add_argument("--prompt", default="pershingsq, aerial view")
    ap.add_argument("--negative", default=None)
    ap.add_argument("--seed", type=int, default=20260728)
    ap.add_argument("--steps", type=int, default=None)
    ap.add_argument("--cfg", type=float, default=None)
    ap.add_argument("--sampler", dest="sampler_name", default=None)
    ap.add_argument("--scheduler", default=None)
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("--run-name", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--assemble-only", metavar="RUN_DIR")
    for role in ("sampler", "lora", "checkpoint", "positive", "negative", "latent", "save"):
        ap.add_argument(f"--node-{role}", dest=f"node_{role}", default=None,
                        help=f"explicit node id for the {role} node")
    args = ap.parse_args()

    if args.assemble_only:
        assemble(args.assemble_only)
        return

    global QUIET_REGISTRY
    QUIET_REGISTRY = args.dry_run

    workflow = strip_comments(load_workflow(args.workflow))
    if args.inspect:
        inspect(workflow)
        return

    # --dry-run deliberately does NOT require a running ComfyUI: previewing
    # the frame list, the detected nodes and the sweep values is exactly what
    # you want to check BEFORE starting the server and committing GPU time.
    # Model-name validation below degrades to a no-op when the registry is
    # unreachable (available() returns []), so the preview still works.
    if not args.dry_run and not ping():
        raise SystemExit(f"ComfyUI not reachable at {COMFY_URL}.\n"
                         "Start it (C:\\ComfyUI_windows_portable\\run_nvidia_gpu.bat) first.")

    if args.list_models:
        print("checkpoints:")
        for c in available("CheckpointLoaderSimple", "ckpt_name"):
            print("   ", c)
        print("loras:")
        for l in available("LoraLoader", "lora_name"):
            print("   ", l)
        return

    roles = autodetect_nodes(workflow, {
        r: getattr(args, f"node_{r}")
        for r in ("sampler", "lora", "checkpoint", "positive", "negative", "latent", "save")})
    print("driving nodes:", ", ".join(f"{r}={n}" for r, n in sorted(roles.items())))

    if args.mode in ("strength", "denoise"):
        if not args.lora:
            raise SystemExit(f"--lora is required in {args.mode} mode "
                             "(--list-models to see options)")
        loras = available("LoraLoader", "lora_name")
        if loras and args.lora not in loras:
            match = [l for l in loras if args.lora.lower() in l.lower()]
            if len(match) != 1:
                raise SystemExit(f"LoRA {args.lora!r} not installed. Available:\n  "
                                 + "\n  ".join(loras))
            args.lora = match[0]
            print(f"resolved --lora to {args.lora}")
        stem = re.sub(r"[^A-Za-z0-9]+", "_", args.lora)[:40]
        if args.mode == "strength":
            jobs = build_jobs_strength(args.lora, parse_sweep(args.sweep))
        else:
            if not args.init_image:
                raise SystemExit("--mode denoise needs --init-image (the screenshot to "
                                 "run through the LoRA)")
            jobs = build_jobs_denoise(args.lora, args.strength, parse_sweep(args.sweep))
        default_run = f"{args.mode}_{stem}"
    else:
        if not args.checkpoints:
            raise SystemExit("--checkpoints is required in checkpoints mode")
        cks = discover_checkpoints(args.checkpoints)
        if not cks:
            raise SystemExit(
                f"no LoRAs matching {args.checkpoints!r}.\n"
                + ("(checkpoints mode enumerates via ComfyUI, so --dry-run needs it "
                   "running too -- unlike strength mode.)\n" if args.dry_run else "")
                + "Checkpoints must live in ComfyUI's models/loras/ to be loadable -- "
                "copy or symlink them there.")
        jobs = build_jobs_checkpoints(cks, not args.no_baseline)
        default_run = re.sub(r"[^A-Za-z0-9]+", "_", args.checkpoints).strip("_")

    opts = {"seed": args.seed, "steps": args.steps, "cfg": args.cfg,
            "sampler_name": args.sampler_name, "scheduler": args.scheduler,
            "prompt": args.prompt, "negative": args.negative, "base": args.base,
            "width": args.width, "height": args.height, "mode": args.mode,
            "init_image": args.init_image, "denoise": args.denoise,
            "workflow": os.path.relpath(args.workflow, BASE_DIR)}
    run_dir = render_series(jobs, workflow, roles, opts,
                            args.run_name or default_run, dry_run=args.dry_run)
    if run_dir:
        assemble(run_dir)
        print(f"\n-> {run_dir}")


if __name__ == "__main__":
    main()
