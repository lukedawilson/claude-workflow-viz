# Tech Stack Decisions — Unit B (hook path / server lifecycle)

| # | Decision | Source |
| --- | --- | --- |
| 1 | `/shutdown` carries the /ingest-equivalent checks only — Bearer token, Host allowlist, loopback-only, no body, 401/204. No additional protection. | NFRB1 = A (open decision 3 closed) |
| 2 | Timeouts: 1s for both `stop_server()` and the reuse probe. | NFRB2 = A |
| 3 | Spawn mechanism: `sys.executable -m claude_workflow_viz serve ...` — pipx-robust, PATH-independent. | NFRB3 = A |
| 4 | Browser-open platforms: macOS `open`, Linux `xdg-open`, Windows `os.startfile` (stdlib, not `cmd /c start`). Selection is one pure function on `sys.platform`; unknown platforms fall back to `xdg-open`. | NFRB4 = B |
| 5 | Windows CI: a GitHub Actions workflow with a `windows-latest` job exercising the win32 branch + full suite. Repo currently has no CI; the workflow file is a Unit B code-generation deliverable. | NFRB4 = B (user condition) |
| 6 | No new runtime dependencies — everything is stdlib (`subprocess`, `sys`, `os`, `hmac`, existing `urllib`). | SECURITY-12 |
| 7 | No PID handling anywhere; the server owns its lifecycle; liveness = `server.json` + probe only. | R1, UEB1 |
