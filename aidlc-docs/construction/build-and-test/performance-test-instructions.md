# Performance Test Instructions

## Purpose

Not applicable. The product is a single-user desktop tool (one loopback
server per machine, one parse per workflow invocation). No load, stress,
or scalability targets exist (NFR Design profile: desktop tool; the only
performance bounds are the 1-second ingest timeout, the 10-second
connection-file wait, and the linear-time parser discipline).

## Performance Requirements

- **Response Time**: no target; parse of a workflow file must complete
  within the 1-second hook timeout (enforced by `tests/test_parser.py`'s
  pathological-fixture test asserting bounded time).
- **Throughput**: N/A.
- **Concurrent Users**: one.
- **Error Rate**: N/A.

The bounded-time regression test is the performance check for this project;
it runs with the unit suite.
