"""3-tier IRC progressive recovery — port from
`D:/code/gaussian-agent/gaussian_agent/handlers/irc_error.py` in Step 5.

Tier 1 (HPC): CalcFC, SCF=XQC, MaxPoints up
Tier 2 (LQA): switch to IRC=(LQA, RecalcFC=5)
Tier 3 (smaller-step): StepSize=5, MaxPoints=20, accept partial path
"""
