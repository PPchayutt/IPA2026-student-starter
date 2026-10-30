import os
from ipaddress import IPv4Interface
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from ncclient import manager
from ncclient.operations.errors import OperationError
from ncclient.transport.errors import AuthenticationError, SSHError, SessionError

from app.backends.planning import plan_interface as build_backend_plan

IETF_IF_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IETF_IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"


def _connect(router):
    user = os.environ.get("ROUTER_USER", "admin")
    password = os.environ.get("ROUTER_PASS", "cisco")
    return manager.connect(
        host=router,
        port=830,
        username=user,
        password=password,
        hostkey_verify=False,
        device_params={"name": "csr"},
        timeout=15,
    )


def _default_get_config(router, filter_xml):
    with _connect(router) as m:
        reply = m.get_config(source="running", filter=("subtree", filter_xml))
        return reply.data_xml


def _default_edit_config(router, config_xml):
    with _connect(router) as m:
        m.edit_config(target="running", config=config_xml)


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    if netconf_get_config is None:
        netconf_get_config = _default_get_config

    filter_xml = f"""<interfaces xmlns="{IETF_IF_NS}">
  <interface>
    <name>{escape(interface_name)}</name>
  </interface>
</interfaces>"""

    try:
        xml_text = netconf_get_config(router, filter_xml)
    except (PermissionError, AuthenticationError):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, TimeoutError, SSHError, SessionError, OSError):
        return {"status": "error", "result": "connection_failed"}
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    try:
        root = ET.fromstring(xml_text)
        iface = root.find(f".//{{{IETF_IF_NS}}}interface")
        if iface is None:
            return {"status": "ok", "result": "not_found", "interface": None}

        name = iface.findtext(f"{{{IETF_IF_NS}}}name")
        description = iface.findtext(f"{{{IETF_IF_NS}}}description")
        enabled_text = (
            iface.findtext(f"{{{IETF_IF_NS}}}enabled", "false").strip().lower()
        )
        admin_state = "up" if enabled_text == "true" else "down"

        addr_elem = iface.find(f"{{{IETF_IP_NS}}}ipv4/{{{IETF_IP_NS}}}address")
        if addr_elem is not None:
            ip = addr_elem.findtext(f"{{{IETF_IP_NS}}}ip")
            netmask = addr_elem.findtext(f"{{{IETF_IP_NS}}}netmask")
            ipv4_cidr = str(IPv4Interface(f"{ip}/{netmask}"))
        else:
            ipv4_cidr = None

        return {
            "status": "ok",
            "result": "found",
            "interface": {
                "name": name,
                "ipv4": ipv4_cidr,
                "description": description,
                "admin_state": admin_state,
            },
        }
    except Exception:
        return {"status": "error", "result": "backend_failed"}


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return build_backend_plan(
        router,
        desired_interface,
        lambda r, name: get_interface_state(
            r, name, netconf_get_config=netconf_get_config
        ),
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    if netconf_edit_config is None:
        netconf_edit_config = _default_edit_config

    try:
        number = str(int(desired_interface["name"][len("Loopback"):]))
        ipv4 = IPv4Interface(desired_interface["ipv4"])
    except Exception:
        return {"status": "error", "result": "backend_failed"}

    shutdown_xml = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""
    desc_escaped = escape(str(desired_interface["description"]))

    config_xml = f"""<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"
        xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
  <native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">
    <interface>
      <Loopback nc:operation="replace">
        <name>{number}</name>
        <description>{desc_escaped}</description>
        <ip>
          <address>
            <primary>
              <address>{ipv4.ip}</address>
              <mask>{ipv4.network.netmask}</mask>
            </primary>
          </address>
        </ip>
        {shutdown_xml}
      </Loopback>
    </interface>
  </native>
</config>"""

    try:
        netconf_edit_config(router, config_xml)
    except (PermissionError, AuthenticationError):
        return {"status": "error", "result": "authentication_failed"}
    except (ConnectionError, TimeoutError, SSHError, SessionError, OSError):
        return {"status": "error", "result": "connection_failed"}
    except (RuntimeError, OperationError, Exception):
        return {"status": "error", "result": "backend_failed"}

    return {"status": "ok", "result": "applied"}
