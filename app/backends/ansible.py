import json
import os
from ipaddress import IPv4Interface
from pathlib import Path
import subprocess

BASE_DIR = Path(__file__).resolve().parents[2]
INVENTORY_PATH = BASE_DIR / "ansible" / "inventory.ini"
PLAYBOOK_PATH = BASE_DIR / "ansible" / "apply_interface.yml"


def _default_run_playbook(variables):
    env = os.environ.copy()
    env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    env["ANSIBLE_NETWORK_CLI_SSH_TYPE"] = "paramiko"

    proc = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(INVENTORY_PATH),
            str(PLAYBOOK_PATH),
            "-e",
            json.dumps(variables),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    if proc.returncode != 0:
        output = f"{proc.stdout}\n{proc.stderr}".lower()
        if (
            "authentication" in output
            or "permission denied" in output
            or "auth fail" in output
            or "invalidiauth" in output
        ):
            raise PermissionError(output)
        if (
            "unreachable" in output
            or "timed out" in output
            or "timeout" in output
            or "connection refused" in output
            or "unable to connect" in output
            or "no route to host" in output
        ):
            raise ConnectionError(output)
        raise RuntimeError(output)


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    if run_playbook is None:
        run_playbook = _default_run_playbook

    try:
        ipv4 = IPv4Interface(desired_interface["ipv4"])
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    variables = {
        "router": router,
        "interface_name": desired_interface["name"],
        "description": desired_interface["description"],
        "ipv4_address": str(ipv4.ip),
        "netmask": str(ipv4.network.netmask),
        "shutdown": desired_interface["admin_state"] == "down",
    }

    try:
        run_playbook(variables)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, subprocess.TimeoutExpired):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    return {"status": "ok", "result": "applied"}
