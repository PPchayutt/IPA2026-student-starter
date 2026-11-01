import os
from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)
from ntc_templates.parse import parse_output


def _normalize_interface_name(name):
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if name.startswith("Lo") and not name.startswith("Loopback"):
        return "Loopback" + name[2:]
    return name


def _connect(router):
    user = os.environ.get("ROUTER_USER", "admin")
    password = os.environ.get("ROUTER_PASS", "cisco")
    return ConnectHandler(
        device_type="cisco_ios",
        host=router,
        username=user,
        password=password,
        timeout=15,
    )


def _query_cli_state(conn, interface_name):
    raw_ip = conn.send_command(
        f"show ip interface {interface_name}",
        use_textfsm=False,
    )
    descriptions = conn.send_command(
        "show interfaces description",
        use_textfsm=True,
    )
    if isinstance(descriptions, str):
        descriptions = []

    raw_lower = raw_ip.lower() if isinstance(raw_ip, str) else ""
    if (
        not raw_lower.strip()
        or "invalid input" in raw_lower
        or "incomplete command" in raw_lower
    ):
        return [], descriptions

    ip_info = parse_output(
        platform="cisco_ios",
        command="show ip interface",
        data=raw_ip,
    )
    ip_info = [
        item
        for item in ip_info
        if str(item.get("link_status", "")).strip().lower() != "deleted"
    ]
    return ip_info, descriptions


def _default_netmiko_get(router, interface_name):
    with _connect(router) as conn:
        return _query_cli_state(conn, interface_name)


def _default_netmiko_delete(router, interface_name):
    with _connect(router) as conn:
        ip_info, _ = _query_cli_state(conn, interface_name)
        exists = any(
            _normalize_interface_name(item.get("interface", "")) == interface_name
            for item in ip_info
        )
        if not exists:
            return "not_found"

        conn.send_config_set([f"no interface {interface_name}"])

        ip_info_after, _ = _query_cli_state(conn, interface_name)
        still_exists = any(
            _normalize_interface_name(item.get("interface", "")) == interface_name
            for item in ip_info_after
        )
        if still_exists:
            raise RuntimeError("Interface still present after delete")
        return "deleted"


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    if netmiko_get is None:
        netmiko_get = _default_netmiko_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
    except (PermissionError, NetmikoAuthenticationException):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, TimeoutError, NetmikoTimeoutException):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if not isinstance(ip_info, list) or not isinstance(descriptions, list):
        return {"status": "error", "result": "backend_failed"}

    try:
        ip_record = None
        for item in ip_info:
            if (
                _normalize_interface_name(item.get("interface", "")) == interface_name
                and str(item.get("link_status", "")).strip().lower() != "deleted"
            ):
                ip_record = item
                break

        if ip_record is None:
            return {"status": "ok", "result": "not_found", "interface": None}

        ip_list = ip_record.get("ip_address") or []
        prefix_list = ip_record.get("prefix_length") or []
        if ip_list and prefix_list:
            ipv4 = f"{ip_list[0]}/{prefix_list[0]}"
        else:
            ipv4 = None

        link_status = str(ip_record.get("link_status", "")).strip().lower()
        admin_state = "down" if link_status == "administratively down" else "up"

        description = None
        for item in descriptions:
            if _normalize_interface_name(item.get("port", "")) == interface_name:
                desc_val = item.get("description")
                description = desc_val if desc_val != "" else None
                break

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": interface_name,
                "ipv4": ipv4,
                "description": description,
                "admin_state": admin_state,
            },
        }
    except Exception:
        return {"status": "error", "result": "backend_failed"}


def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    if netmiko_delete is None:
        netmiko_delete = _default_netmiko_delete

    try:
        delete_result = netmiko_delete(router, interface_name)
    except (PermissionError, NetmikoAuthenticationException):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, TimeoutError, NetmikoTimeoutException):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    if delete_result == "deleted":
        return {"status": "ok", "result": "deleted"}
    if delete_result == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}
    return {"status": "error", "result": "backend_failed"}
