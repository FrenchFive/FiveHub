"""Rendering: job submission and execution.

A render is a job in the project database. Any machine running the FiveHub
worker (``python -m fivehub.cli worker``) picks it up, opens the scene in
``hython``, drives the chosen ROP over the shot's frame range, and registers
the frames as a versioned ``render`` publish under
``<task>/publish/render/v###/``. When ffmpeg is on the worker's PATH an
encode job follows automatically and drops a ``preview.mp4`` next to the
frames — the dailies file.
"""

import os
import re
import shutil
import subprocess

from . import config
from .report import RuleResult, Status, ValidationReport
from .user import get_user

ENV_HYTHON = "FIVEHUB_HYTHON"
ENV_HOUDINI = "FIVEHUB_HOUDINI"

# Output-image parameter names per ROP family, tried in order.
OUTPUT_PARMS = ("vm_picture", "picture", "RS_outputFileNamePrefix", "ar_picture",
                "outputimage", "copoutput", "sopoutput")


def resolve_hython():
    explicit = os.environ.get(ENV_HYTHON, "").strip()
    if explicit:
        return explicit
    found = shutil.which("hython")
    if found:
        return found
    houdini = os.environ.get(ENV_HOUDINI, "").strip()
    if houdini:
        sibling = os.path.join(os.path.dirname(houdini), "hython")
        if os.path.isfile(sibling):
            return sibling
        if os.path.isfile(sibling + ".exe"):
            return sibling + ".exe"
    return None


def _render_report(name, frames, user):
    report = ValidationReport(asset_name=name, user=user)
    report.results.append(
        RuleResult(
            "render.frames",
            "Frames were rendered",
            "error",
            Status.PASS if frames else Status.FAIL,
            [] if frames else ["no frames were produced"],
        )
    )
    return report


def submit_render(project, kind, entity, task, scene_version, rop,
                  frame_start=None, frame_end=None, step=1, user=""):
    """Queue a render job for a saved scene version."""
    scene = project.get_scene(kind, entity, task, scene_version)
    if scene is None:
        raise ValueError("no scene v%03d on that task" % int(scene_version))
    meta = project.db.get_entity(kind, entity) or {}
    settings = project.settings()
    payload = {
        "kind": kind,
        "entity": entity,
        "task": task,
        "scene_version": int(scene_version),
        "scene_file": project.rel(scene["file"]),
        "rop": rop,
        "frame_start": int(
            frame_start if frame_start is not None
            else meta.get("frame_start") or settings["frame_start"]
        ),
        "frame_end": int(
            frame_end if frame_end is not None
            else meta.get("frame_end") or settings["frame_end"]
        ),
        "step": int(step or 1),
        "fps": float(meta.get("fps") or settings["fps"]),
    }
    user = user or get_user()
    job_id = project.db.enqueue_job("render", payload, user=user)
    return {"job_id": job_id, **payload}


def _hython_script(scene_file, rop, output_pattern, frame_start, frame_end, step):
    # Runs inside hython on the worker. Output override is best-effort:
    # if the ROP's image parm isn't recognized, it renders to its own
    # configured path and says so.
    return r"""
import hou, sys
hou.hipFile.load({scene!r}, suppress_save_prompt=True, ignore_load_warnings=True)
rop = hou.node({rop!r})
if rop is None:
    sys.stderr.write("ROP not found: " + {rop!r} + "\n")
    sys.exit(2)
overridden = False
for parm_name in {parms!r}:
    parm = rop.parm(parm_name)
    if parm is not None:
        parm.set({output!r})
        overridden = True
        break
if not overridden:
    sys.stderr.write("WARNING: no known output parm on " + {rop!r} +
                     " - rendering to its own configured path\n")
for parm_name, value in (("trange", 1), ("f1", {f0}), ("f2", {f1}), ("f3", {f2})):
    parm = rop.parm(parm_name)
    if parm is not None:
        try:
            parm.deleteAllKeyframes()
        except Exception:
            pass
        parm.set(value)
rop.render(frame_range=({f0}, {f1}, {f2}), verbose=True, output_progress=True)
""".format(
        scene=scene_file, rop=rop, parms=OUTPUT_PARMS, output=output_pattern,
        f0=frame_start, f1=frame_end, f2=step,
    )


def run_render_job(project, job):
    """Execute a render job (called by the worker). Returns (status, log)."""
    payload = job["payload"]
    kind, entity, task = payload["kind"], payload["entity"], payload["task"]
    scene_file = project.absolute(payload["scene_file"])
    if not os.path.isfile(scene_file):
        return "failed", "scene file is missing: %s" % scene_file

    hython = resolve_hython()
    if hython is None:
        return "failed", (
            "hython not found on this worker. Set FIVEHUB_HYTHON (or "
            "FIVEHUB_HOUDINI) so the worker can render."
        )

    name = "%s_%s" % (entity, task)
    version = project.claim_publish(
        kind, entity, task, name, "render", "default", job.get("user", "")
    )
    label = config.version_label(version)
    version_dir = os.path.join(
        project.publish_dir(kind, entity, task, "render"), label
    )
    os.makedirs(version_dir, exist_ok=True)
    output_pattern = os.path.join(version_dir, "%s_%s.$F4.exr" % (name, label))

    script = _hython_script(
        scene_file, payload["rop"], output_pattern,
        payload["frame_start"], payload["frame_end"], payload["step"],
    )
    try:
        completed = subprocess.run(
            [hython, "-c", script], capture_output=True, text=True, timeout=86400
        )
        log = (completed.stdout or "") + "\n" + (completed.stderr or "")
        returncode = completed.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        log = str(error)
        returncode = 1

    frames = [
        entry for entry in sorted(os.listdir(version_dir))
        if entry.lower().endswith((".exr", ".png", ".jpg", ".jpeg", ".tif", ".tiff"))
    ] if os.path.isdir(version_dir) else []

    if returncode != 0 or not frames:
        project.release_publish(kind, entity, task, "render", version)
        shutil.rmtree(version_dir, ignore_errors=True)
        return "failed", "render failed (exit %s)\n%s" % (returncode, log[-8000:])

    report = _render_report(name, frames, job.get("user", ""))
    report_path = report.save(os.path.join(version_dir, config.REPORT_FILE))
    project.complete_publish(
        kind, entity, task, "render", version, report,
        path=version_dir, report_path=report_path,
        comment="%s %s-%s @%s" % (
            payload["rop"], payload["frame_start"], payload["frame_end"],
            payload["step"],
        ),
        user=job.get("user", ""),
    )

    # Dailies: encode automatically when ffmpeg is available anywhere.
    if shutil.which("ffmpeg"):
        project.db.enqueue_job(
            "encode",
            {"render_dir": project.rel(version_dir), "fps": payload["fps"]},
            user=job.get("user", ""),
        )
    return "done", "rendered %d frame(s) into %s\n%s" % (
        len(frames), version_dir, log[-4000:]
    )


_FRAME_RE = re.compile(r"^(.*?)(\d+)(\.[A-Za-z]+)$")


def run_encode_job(project, job):
    """Encode a rendered frame sequence to preview.mp4 (called by worker)."""
    render_dir = project.absolute(job["payload"].get("render_dir", ""))
    fps = float(job["payload"].get("fps") or 24)
    if not os.path.isdir(render_dir):
        return "failed", "render directory is missing: %s" % render_dir
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "failed", "ffmpeg not found on this worker"

    sequences = {}
    for entry in sorted(os.listdir(render_dir)):
        match = _FRAME_RE.match(entry)
        if match and match.group(3).lower() in (".exr", ".png", ".jpg", ".jpeg"):
            prefix, number, extension = match.groups()
            sequences.setdefault((prefix, len(number), extension), []).append(
                int(number)
            )
    if not sequences:
        return "failed", "no frame sequence found in %s" % render_dir

    (prefix, padding, extension), numbers = max(
        sequences.items(), key=lambda item: len(item[1])
    )
    pattern = os.path.join(render_dir, "%s%%0%dd%s" % (prefix, padding, extension))
    target = os.path.join(render_dir, "preview.mp4")
    command = [
        ffmpeg, "-y", "-framerate", str(fps), "-start_number", str(min(numbers)),
        "-i", pattern, "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", target,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    if completed.returncode != 0 or not os.path.isfile(target):
        return "failed", (completed.stderr or "ffmpeg failed")[-8000:]
    return "done", "encoded %s (%d frames @ %s fps)" % (target, len(numbers), fps)
