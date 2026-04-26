"""M.0 vertical-slice spike — minimal L2 pipeline.

This package is intentionally throwaway: the goal is to validate the L2
pipeline shape (CLI → schema → data → dashboard → handbook) end-to-end on
the smallest possible scenario. Working primitives lift into proper library
code under `common/l2/` in M.1; the spike package goes away after M.0.13's
iteration gate.

See `tests/spike/_l2_spike_findings.md` for what we've learned so far.
"""
