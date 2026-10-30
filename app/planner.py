def build_plan(desired_interface, current_interface):
    """
    Compare desired interface state with normalized current state
    and return a plan according to specs/plan-spec-v1.md.
    """
    if current_interface is None:
        return {
            "status": "ok",
            "result": "planned",
            "operation": "create",
            "changes" : {
                "ipv4": {"to": desired_interface["ipv4"]},
                "description": {"to": desired_interface["description"]},
                "admin_state": {"to": desired_interface["admin_state"]},
            },
        }

    changes = {}
    for field in ("ipv4", "description", "admin_state"):
        if current_interface[field] != desired_interface[field]:
            changes[field] = {
                "from": current_interface[field],
                "to": desired_interface[field],
            }

    if changes:
        operation = "update"
    else:
        operation = "no_change"

    return {
        "status": "ok",
        "result": "planned",
        "operation": operation,
        "changes": changes,
    }
