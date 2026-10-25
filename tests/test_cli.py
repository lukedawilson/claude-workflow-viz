from pathlib import Path

import pytest

from _platform import path_with_console_scripts
from claude_workflow_viz.cli import main


def test_no_subcommand_exits_non_zero_with_usage(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code != 0
    assert "usage:" in capsys.readouterr().err


def test_unknown_subcommand_exits_non_zero_with_usage(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["bogus"])
    assert exit_info.value.code != 0
    assert "usage:" in capsys.readouterr().err


def test_help_lists_serve_hook_and_install(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0
    output = capsys.readouterr().out
    assert "serve" in output
    assert "hook" in output
    assert "install" in output


def test_hook_subcommand_returns_zero():
    assert main(["hook"]) == 0


def _clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_WORKFLOW_VIZ_STATE_DIR", str(tmp_path))


def test_serve_with_invalid_graph_exits_non_zero_and_writes_no_connection_file(
    tmp_path, monkeypatch, capsys
):
    _clean_environment(tmp_path, monkeypatch)
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n")
    code = main(["serve", "--graph", str(bad)])
    assert code != 0
    assert "graph" in capsys.readouterr().err.lower()
    assert not (tmp_path / "server.json").exists()


def test_serve_with_missing_graph_file_exits_non_zero(tmp_path, monkeypatch, capsys):
    _clean_environment(tmp_path, monkeypatch)
    assert main(["serve", "--graph", str(tmp_path / "nope.yaml")]) != 0
    assert "nope.yaml" in capsys.readouterr().err
    assert not (tmp_path / "server.json").exists()


def test_serve_prints_ui_url_with_token_and_exposes_graph(tmp_path, monkeypatch):
    import http.client
    import io
    import json
    import re
    import threading
    import time

    from claude_workflow_viz.dashboard import server as server_module

    _clean_environment(tmp_path, monkeypatch)
    example = Path(__file__).parent.parent / "examples" / "implement.viz.yaml"

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    stdout = Terminal()
    monkeypatch.setattr(server_module.sys, "stdout", stdout)
    result = []
    original = server_module.VisualiserServer.serve_forever

    def stop_after_probe(self, *args, **kwargs):
        def probe():
            result.append(stdout.getvalue())
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            connection.request("GET", f"/graph?token={self.token}")
            result.append(json.loads(connection.getresponse().read())["source"])
            self.shutdown()

        threading.Thread(target=probe, daemon=True).start()
        time.sleep(0)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(server_module.VisualiserServer, "serve_forever", stop_after_probe)
    assert main(["serve", "--graph", str(example)]) == 0
    assert re.search(r"http://127\.0\.0\.1:\d+/\?token=\S+", result[0])
    assert result[1] == "config"


def test_install_writes_into_cwd_and_prints_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", path_with_console_scripts())
    assert main(["install"]) == 0
    output = capsys.readouterr().out
    assert "run a workflow to see the dashboard" in output
    assert (tmp_path / ".claude" / "settings.local.json").exists()
    assert (tmp_path / ".claude" / "commands" / "viz.md").exists()


def test_install_missing_binary_prints_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    assert main(["install"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "claude-workflow-viz" in captured.err
    assert not (tmp_path / ".claude").exists()


def test_install_force_and_viz_dir_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", path_with_console_scripts())
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "viz.md").write_text("old", encoding="utf-8")
    assert main(["install", "--force", "--viz-dir", "custom/viz"]) == 0
    output = capsys.readouterr().out
    assert "command: forced" in output
    command = (tmp_path / ".claude" / "commands" / "viz.md").read_text(encoding="utf-8")
    assert "custom/viz" in command
    assert "old" not in command
