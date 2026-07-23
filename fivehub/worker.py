"""The FiveHub worker: executes queued jobs (renders, encodes).

Run it on the server — or any workstation with Houdini — with:

    python -m fivehub.cli worker            # all projects, forever
    python -m fivehub.cli worker --project X --once

Jobs are claimed atomically from each project's database, so several
workers can run side by side without stepping on each other.
"""

import os
import socket
import time

from . import render
from .project import get_project, list_projects
from .user import get_user

HANDLERS = {
    "render": render.run_render_job,
    "encode": render.run_encode_job,
}


def worker_id():
    return "%s@%s:%d" % (get_user() or "worker", socket.gethostname(), os.getpid())


def run_once(hub_root=None, project_name=None, log=print):
    """One pass over the queue(s); returns the number of jobs executed."""
    if project_name:
        names = [project_name]
    else:
        names = [info["name"] for info in list_projects(hub_root)]
    executed = 0
    me = worker_id()
    for name in names:
        project = get_project(name, hub_root)
        while True:
            job = project.db.claim_job(me)
            if job is None:
                break
            handler = HANDLERS.get(job["type"])
            log("[%s] %s job %s in %s" % (me, job["type"], job["id"][:8], name))
            if handler is None:
                project.db.finish_job(job["id"], "failed",
                                      "unknown job type %r" % job["type"])
                continue
            try:
                status, job_log = handler(project, job)
            except Exception as error:  # a broken job must never kill the worker
                status, job_log = "failed", "worker exception: %r" % error
            project.db.finish_job(job["id"], status, job_log)
            log("[%s]   -> %s" % (me, status))
            executed += 1
    return executed


def run_forever(hub_root=None, project_name=None, poll_seconds=5, log=print):
    log("FiveHub worker %s started (poll %ss)" % (worker_id(), poll_seconds))
    try:
        while True:
            executed = run_once(hub_root, project_name, log=log)
            if not executed:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        log("worker stopped")
