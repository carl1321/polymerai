# IRC recovery tiers

| Tier | Strategy | Gaussian flags |
|---|---|---|
| 1 HPC | tighten SCF + CalcFC | `IRC=(CalcFC,MaxPoints=80) SCF=(XQC,MaxCycle=200)` |
| 2 LQA | switch integrator | `IRC=(LQA,RecalcFC=5,MaxPoints=50)` |
| 3 smaller-step | reduce step, accept partial | `IRC=(MaxPoints=20,StepSize=5)` |

Port rules from legacy `gaussian_agent/handlers/irc_error.py` during Step 5.
