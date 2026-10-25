# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0a1] - 2026-10-25

### Changed

- Log the shutdown race fix in the audit
- Fix /shutdown race: close the socket only on the main thread
- Publishing machinery
- Mark AI-DLC session complete in state file
- Close AI-DLC session: operations stage has no work for a desktop tool
- Add Build and Test gate artifacts and stage bookkeeping
- Fix serve-shutdown test connection read and viz-dir path assertions for Windows
- Sort imports after platform-aware test edits
- Make POSIX-only tests platform-aware so the Windows CI job passes
- Log demo terminal fix in audit
- Fix demo terminal rendering: fixture events now satisfy the ingest contract
- Light terminal nodes green when the run hits them
- Fix demo skip rendering: replay events with run_id; add demo-progression regression test
- Extend run-demo.sh with a skipped stage (Unit D demo); Unit D approval bookkeeping
- feat: construct unit unit-d-skipped-stage (agent dev loop)
- feat: construct unit unit-c-install (agent dev loop)
- Install unit docs
- Extend run-demo.sh to the full progression with hold, fix interpreter default
- feat: construct unit unit-b-hook-path (agent dev loop)
- Docs
- feat: construct unit unit-a-graph-source (agent dev loop)
- Initial commit

