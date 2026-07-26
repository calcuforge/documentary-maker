"""Shared JSON envelope + exit-code conventions for documentary-maker CLI scripts.

Envelope shape:
    { "status": "ok" | "warning" | "error",
      "data":   {...},     # present on ok / warning
      "error":   { "code": "...", "message": "...", "details": "..." }  # present on error
    }

Exit codes:
    0 — ok (or warnings that are still acceptable)
    1 — workflow execution failure (server-side, file missing, etc.)
    2 — usage error (missing required option, invalid args)
    3 — confirmation_required (destructive migration / overwrite)

CLI scripts accept `--format json|text` (default `text`). When `--format json`
is set OR stdout is piped, the envelope is printed to stdout as one JSON line.
"""
import json
import sys

OK = 0
USAGE = 2
CONFIRMATION_REQUIRED = 3
FAILURE = 1


def emit_ok(data=None, message=None, fmt="text"):
    _emit("ok", data=data, message=message, fmt=fmt, exit_code=OK)


def emit_warning(data=None, message=None, fmt="text"):
    _emit("warning", data=data, message=message, fmt=fmt, exit_code=OK)


def emit_error(code, message, details=None, fmt="text", exit_code=FAILURE):
    _emit("error", error={"code": code, "message": message, "details": details},
          fmt=fmt, exit_code=exit_code)


def emit_usage_error(message, details=None, fmt="text"):
    _emit("error", error={"code": "usage", "message": message, "details": details},
          fmt=fmt, exit_code=USAGE)


def emit_confirmation_required(message, details=None, fmt="text"):
    _emit("error", error={"code": "confirmation_required", "message": message,
                          "details": details},
          fmt=fmt, exit_code=CONFIRMATION_REQUIRED)


def _emit(status, data=None, error=None, message=None, fmt="text", exit_code=0):
    if fmt == "json" or not sys.stdout.isatty():
        payload = {"status": status}
        if data is not None:
            payload["data"] = data
        if error is not None:
            payload["error"] = error
        if message is not None:
            payload["message"] = message
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        if message:
            sys.stderr.write(message + "\n")
        if data is not None:
            sys.stderr.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        if error is not None:
            sys.stderr.write(f"error: {error['message']}\n")
            if error.get("details"):
                sys.stderr.write(f"  details: {error['details']}\n")
    sys.exit(exit_code)


def add_format_arg(parser):
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format. `json` is auto-selected when stdout is piped.",
    )
    return parser
