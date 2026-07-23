"""Artist identity — the lightweight "login".

Publishes and scene saves are signed with a name and a timestamp for
traceability. The name comes from, in order:

    1. the FIVEHUB_USER environment variable
    2. the per-machine login file (~/.fivehub/user.json), written by
       ``fivehub.cli login <name>`` or the hub app's login sheet
    3. the OS account name as a fallback

The login file is per-machine on purpose: hubs often live on shared
drives, but the person at the workstation is local.
"""

import getpass
import json
import os

ENV_USER = "FIVEHUB_USER"
ENV_USER_FILE = "FIVEHUB_USER_FILE"


def user_file():
    return os.environ.get(ENV_USER_FILE) or os.path.join(
        os.path.expanduser("~"), ".fivehub", "user.json"
    )


def get_user():
    """The name every publish and scene save is signed with."""
    from_env = os.environ.get(ENV_USER, "").strip()
    if from_env:
        return from_env
    try:
        with open(user_file(), "r", encoding="utf-8") as handle:
            name = str(json.load(handle).get("name", "")).strip()
            if name:
                return name
    except (OSError, ValueError):
        pass
    try:
        return getpass.getuser()
    except Exception:
        return ""


def set_user(name):
    name = str(name or "").strip()
    if not name:
        raise ValueError("a name is required to sign publishes")
    path = user_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"name": name}, handle, indent=2)
    return name


def logged_in():
    """True when a name was set explicitly (env or login file)."""
    if os.environ.get(ENV_USER, "").strip():
        return True
    try:
        with open(user_file(), "r", encoding="utf-8") as handle:
            return bool(str(json.load(handle).get("name", "")).strip())
    except (OSError, ValueError):
        return False
