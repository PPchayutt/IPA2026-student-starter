import os
from ipaddress import IPv4Interface
import requests
from app.backends.planning import plan_interface as build_backend_plan

HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}


def _default_http_get(url):
    user = os.environ.get("ROUTER_USER", "admin")
    password = os.environ.get("ROUTER_PASS", "cisco")
    return requests.get(
        url,
        auth=(user, password),
        headers=HEADERS,
        verify=False,
        timeout=10,
    )


def _default_http_put(url, json):
    user = os.environ.get("ROUTER_USER", "admin")
    password = os.environ.get("ROUTER_PASS", "cisco")
    return requests.put(
        url,
        auth=(user, password),
        headers=HEADERS,
        json=json,
        verify=False,
        timeout=10,
    )


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    if http_get is None:
        http_get = _default_http_get

    url = (
        f"https://{router}/restconf/data/"
        f"ietf-interfaces:interfaces/interface={interface_name}"
    )

    try:
        response = http_get(url)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (
        ConnectionError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if response.status_code in (401, 403):
        return {"status": "error", "result": "authentication_failed"}
    if response.status_code == 404:
        return {"status": "ok", "result": "not_found", "interface": None}
    if response.status_code != 200:
        return {"status": "error", "result": "backend_failed"}

    try:
        iface = response.json()["ietf-interfaces:interface"]
        addrs = iface.get("ietf-ip:ipv4", {}).get("address", [])
        if addrs:
            ip = addrs[0]["ip"]
            netmask = addrs[0]["netmask"]
            ipv4_cidr = str(IPv4Interface(f"{ip}/{netmask}"))
        else:
            ipv4_cidr = None

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": iface["name"],
                "ipv4": ipv4_cidr,
                "description": iface.get("description"),
                "admin_state": "up" if iface.get("enabled") else "down",
            },
        }
    except Exception:
        return {"status": "error", "result": "backend_failed"}


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return build_backend_plan(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get=http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    if http_put is None:
        http_put = _default_http_put

    try:
        number = int(desired_interface["name"][len("Loopback"):])
        ipv4 = IPv4Interface(desired_interface["ipv4"])
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    url = (
        f"https://{router}/restconf/data/"
        f"Cisco-IOS-XE-native:native/interface/Loopback={number}"
    )

    loopback_data = {
        "name": number,
        "description": desired_interface["description"],
        "ip": {
            "address": {
                "primary": {
                    "address": str(ipv4.ip),
                    "mask": str(ipv4.network.netmask),
                }
            }
        },
    }
    if desired_interface["admin_state"] == "down":
        loopback_data["shutdown"] = [None]

    payload = {"Cisco-IOS-XE-native:Loopback": loopback_data}

    try:
        response = http_put(url, json=payload)
    except PermissionError:
        return {"status": "error", "result": "authentication_failed"}
    except (
        ConnectionError,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
    ):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if response.status_code in (200, 201, 204):
        return {"status": "ok", "result": "applied"}
    if response.status_code in (401, 403):
        return {"status": "error", "result": "authentication_failed"}
    return {"status": "error", "result": "backend_failed"}
