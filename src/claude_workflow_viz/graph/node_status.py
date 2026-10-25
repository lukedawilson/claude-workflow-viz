"""Display status derived from the shared rules in `status_rules.json`."""

import json
from collections.abc import Mapping
from importlib import resources
from typing import Any

_RULES = json.loads(
    resources.files("claude_workflow_viz")
    .joinpath("static/status_rules.json")
    .read_text(encoding="utf-8")
)
_FIELDS: list[str] = _RULES["fields"]
_VERDICTS: dict[str, str] = {
    verdict.lower(): status for verdict, status in _RULES["verdicts"].items()
}


def verdict_status(result: Any) -> str | None:
    """Return the pass/fail status of `result`, or None when it holds no recognised verdict.

    Fields are read in rule order, case-insensitive; the first recognised verdict wins.
    """
    if not isinstance(result, Mapping):
        return None
    for name in _FIELDS:
        value = result.get(name)
        if isinstance(value, str) and value.lower() in _VERDICTS:
            return _VERDICTS[value.lower()]
    return None
