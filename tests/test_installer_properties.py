"""Property-based invariants for the settings merge, template render and semantic presence.

These properties pin the NFRC4-A/PBT targets: the merge is a byte fixpoint, the template render
is idempotent and always records the viz-dir, and presence depends only on the command string,
never on surrounding keys or their order.
"""

import json
import string

import pytest

from claude_workflow_viz.install import installer

hypothesis = pytest.importorskip("hypothesis")
assume = hypothesis.assume
given = hypothesis.given
settings = hypothesis.settings
st = hypothesis.strategies

_json_value = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(alphabet=string.printable),
    lambda children: (
        st.lists(children)
        | st.dictionaries(st.text(alphabet=string.ascii_letters, min_size=1), children)
    ),
    max_leaves=12,
)


@st.composite
def json_mappings(draw):
    """An arbitrary JSON-compatible top-level mapping (the merge only cares about 'hooks')."""
    return draw(
        st.dictionaries(st.text(alphabet=string.ascii_letters, min_size=1), _json_value, max_size=8)
    )


@given(json_mappings())
@settings(max_examples=100, deadline=None)
def test_merge_is_a_byte_fixpoint(document):
    first = installer._merge(document, installer._missing_registrations(document))
    first_bytes = installer._settings_text(first)
    reloaded = json.loads(first_bytes)
    second = installer._merge(reloaded, installer._missing_registrations(reloaded))
    assert installer._settings_text(second) == first_bytes


@given(st.text(max_size=100))
@settings(max_examples=100, deadline=None)
def test_render_contains_the_viz_dir_and_is_idempotent(viz_dir):
    assume(installer.VIZ_DIR_PLACEHOLDER not in viz_dir)
    rendered = installer._render_viz_command(viz_dir)
    assert viz_dir in rendered
    # Substituting again into the rendered text changes nothing.
    assert rendered.replace(installer.VIZ_DIR_PLACEHOLDER, viz_dir) == rendered


@given(st.dictionaries(st.text(max_size=10), st.text(max_size=10), max_size=5))
@settings(max_examples=100, deadline=None)
def test_presence_depends_only_on_the_command_string(extra):
    # A registration with the right command counts as present however it is surrounded.
    assert installer._contains_registration({**extra, "command": installer.HOOK_COMMAND})
    # The same surroundings with any other command do not count.
    assert not installer._contains_registration({**extra, "command": "some other command"})
