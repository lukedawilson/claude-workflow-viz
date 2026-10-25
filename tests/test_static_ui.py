"""Static checks on the web UI files. Browser rendering is checked by hand (see the README)."""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

STATIC = Path(__file__).parent.parent / "src" / "claude_workflow_viz" / "static"
VENDORED = {"mermaid.min.js", "mermaid.LICENSE"}
URL = re.compile(r"https?://", re.IGNORECASE)


def _static_files() -> list[Path]:
    return sorted(path for path in STATIC.iterdir() if path.is_file())


def test_vendored_mermaid_matches_the_recorded_sha256() -> None:
    notes = (STATIC / "VENDORED.md").read_text("utf-8")
    recorded = re.search(r"sha256:\s*`?([0-9a-f]{64})`?", notes)
    assert recorded is not None, "VENDORED.md must record `sha256: <hex>`"
    assert re.search(r"version:\s*`?11\.\d+\.\d+`?", notes), "VENDORED.md must record version 11.x"
    actual = hashlib.sha256((STATIC / "mermaid.min.js").read_bytes()).hexdigest()
    assert actual == recorded.group(1)
    assert (STATIC / "mermaid.LICENSE").read_text("utf-8").strip()


def test_no_static_file_loads_an_external_url() -> None:
    """Every file found by listing static/ is scanned. The vendored bundle holds XML namespace
    URLs in its code, so it is only checked for external script, style and link sources."""
    names = {path.name for path in _static_files()}
    assert {"index.html", "app.js", "styles.css", "viz-core.js"} <= names
    for path in _static_files():
        text = path.read_text("utf-8")
        if path.name in VENDORED:
            external_source = re.search(r"""(?:src|href)\s*=\s*["']\s*(?:https?:)?//""", text)
            assert not external_source, f"{path.name} loads an external source"
            continue
        assert not URL.search(text), f"{path.name} contains an http(s) URL"
        assert not re.search(r"""(?:src|href)\s*=\s*["']\s*//""", text), path.name
        assert not re.search(r"""@import\s+(?:url\()?["']?\s*//""", text), path.name


class _Sources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.scripts.append(dict(attrs).get("src") or "")


def test_index_loads_mermaid_and_app_by_relative_static_paths() -> None:
    parser = _Sources()
    parser.feed((STATIC / "index.html").read_text("utf-8"))
    assert "/static/mermaid.min.js" in parser.scripts
    assert "/static/app.js" in parser.scripts
    assert parser.scripts.index("/static/mermaid.min.js") < parser.scripts.index("/static/app.js")
    assert all(source.startswith("/static/") for source in parser.scripts)


def test_app_never_assigns_event_data_through_innerhtml() -> None:
    """The only innerHTML assignments allowed are a constant string literal or a call to
    escapeHtml(...). Everything else must use textContent or createElement."""
    source = (STATIC / "app.js").read_text("utf-8")
    assignments = re.findall(r"\.(?:innerHTML|outerHTML)\s*=\s*([^;]+);", source)
    assert not re.search(r"insertAdjacentHTML|document\.write", source)
    for value in assignments:
        value = value.strip()
        constant = re.fullmatch(r"""(?:"[^"$\\]*"|'[^'$\\]*'|`[^`$\\]*`)""", value)
        escaped = re.fullmatch(r"escapeHtml\(.*\)", value, re.DOTALL)
        assert constant or escaped, f"unsafe innerHTML assignment: {value}"


def test_app_renders_only_from_the_graph_changed_guard() -> None:
    source = (STATIC / "app.js").read_text("utf-8")
    assert len(re.findall(r"mermaid\.render\(", source)) == 1
    render_at = source.index("mermaid.render(")
    function_at = source.rfind("function ", 0, render_at)
    assert "graphChanged(" in source[function_at:render_at], (
        "mermaid.render must sit behind the graphChanged comparison"
    )


def test_every_static_file_has_a_content_type() -> None:
    from claude_workflow_viz.dashboard.server import _CONTENT_TYPES

    not_served = {"VENDORED.md", "mermaid.LICENSE"}  # ship in the package, never served
    for path in _static_files():
        if path.name not in not_served:
            assert path.suffix in _CONTENT_TYPES, f"{path.name} would fail to serve"
