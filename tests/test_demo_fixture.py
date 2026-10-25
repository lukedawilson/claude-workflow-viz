"""Lock the demo-progression fixture to the /ingest contract.

Every event in tests/fixtures/demo-progression.json must pass Event.from_dict:
the server drops any event that fails validation, and a dropped event is a
silently missing node in the dashboard. This test makes that failure loud.
"""

import json
from pathlib import Path

from claude_workflow_viz.workflow.events import Event


def test_every_demo_progression_event_passes_event_from_dict() -> None:
    fixture = Path(__file__).parent / "fixtures" / "demo-progression.json"
    events = json.loads(fixture.read_text())
    assert events, "fixture must not be empty"
    for index, payload in enumerate(events):
        parsed = Event.from_dict(payload)
        assert isinstance(parsed, Event), f"event {index} rejected: {parsed}"
