import yaml

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.
    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}

    # 1. Version
    version = data.get("version")
    if version != 1 or not isinstance(version, int) or isinstance(version, bool):
        return {"status": "error", "result": "invalid_version"}

    # 2. Router
    ALLOWED_ROUTERS = {
        "10.0.29.101", "10.0.29.102", "10.0.29.103", "10.0.29.104", "10.0.29.105"
    }
    if "router" not in data or data["router"] is None:
        return{"status": "error", "result": "missing_router"}
    if data["router"] not in ALLOWED_ROUTERS:
        return{"status": "error", "result": "invalid_router"}

    # 3. method
    ALLOWED_METHODS = {"restconf", "netconf", "ansible", "netmiko-textfsm"}
    if "method" not in data or data["method"] is None:
        return{"status": "error", "result": "missing_method"}
    if data["method"] not in ALLOWED_METHODS:
        return{"status": "error", "result": "invalid_method"}

    # 4. action
    VALID_METHOD_ACTIONS = {
        "restconf": {"status", "plan", "apply"},
        "netconf" : {"status", "plan", "apply"},
        "ansible" : {"apply"},
        "netmiko-textfsm" : {"status", "delete"},
    }
    if "action" not in data or data["action"] is None:
        return {"status": "error", "result" : "missing_action"}
    if data["action"] not in VALID_METHOD_ACTIONS.get(data["method"], set()):
        return {"status": "error", "result": "invalid_action"}

    # 5. desired, interface, name
    desired = data.get("desired")
    if not isinstance(desired, dict):
        return {"status": "error", "result": "missing_desired"}
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return {"status": "error", "result": "missing_interface"}
    name = interface.get("name")
    if not isinstance(name, str) or name == "":
        return {"status": "error", "result": "missing_interface_name"}

    # 6. only for plan and apply
    if data["action"] in {"plan", "apply"}:
        if not interface.get("ipv4"):
            return {"status": "error", "result": "missing_ipv4"}
        if not interface.get("description"):
            return {"status": "error", "result": "missing_description"}
        if "admin_state" not in interface or interface["admin_state"] is None:
            return {"status": "error", "result": "missing_admin_state"}
        if interface["admin_state"] not in {"up", "down"}:
            return {"status": "error", "result": "invalid_admin_state"}

    # ถ้าผ่านเงื่อนไขด้านบนมาได้ทั้งหมด
    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError:
        return {"status": "error", "result": "invalid_yaml"}

    return validate_request(data)
