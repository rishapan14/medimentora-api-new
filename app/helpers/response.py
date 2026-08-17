"""Standardized JSON API response helpers."""

from flask import jsonify


def success_response(message, data=None, status_code=200):
    """Return a consistent success JSON response."""
    return jsonify({
        "status": "success",
        "message": message,
        "data": data,
    }), status_code


def error_response(message, status_code=400, data=None):
    """Return a consistent error JSON response."""
    return jsonify({
        "status": "error",
        "message": message,
        "data": data,
    }), status_code
