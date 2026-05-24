from flask import jsonify


def error_response(message, status_code, details=None):
    payload = {"error": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code
