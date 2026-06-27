import json


def make_status_json(**payload) -> str:
    return json.dumps(payload, sort_keys=True)
