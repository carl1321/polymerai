"""IRC progressive-recovery handler.

**Core asset — port in Step 5 of PLAN.md.**

Reference implementation:
    D:/code/gaussian-agent/gaussian_agent/handlers/irc_error.py

Three-tier degradation strategy when IRC fails:
    1. HPC: tighten SCF, add CalcFC, larger maxpoints
    2. LQA: switch integrator to IRC=(LQA)
    3. smaller-step: reduce step size / maxpoints, allow partial paths

This is independent Gaussian IP; do not simplify into a single retry.
"""
