import yaml

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.
    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
        return {"status": "error", "result": "invalid_yaml"}
    version = data.get("version")

    # 1. Version
    if version != 1 or not isinstance(version, int) or isinstance(version, bool):
        return {"status": "error", "result": "invalid_version"}

    # 2. Router
    ALLOWED_ROUTERS = {
        "10.0.29.101", "10.0.29.102", "10.0.29.103", "10.0.29.104", "10.0.29.105"
    }
    



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

