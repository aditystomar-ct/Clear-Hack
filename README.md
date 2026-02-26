# DPA Contract Review Tool

AI-powered Data Processing Agreement review system for ClearTax. Compares incoming DPAs against your standard DPA and internal rulebook using Claude, flags risky clauses, and syncs findings back to Google Docs as comments and highlights.

## What It Does

1. Paste a Google Doc URL containing an incoming DPA
2. Claude analyzes every clause against your standard DPA template + rulebook
3. Flags risky clauses with risk levels (High/Medium/Low), explanations, and suggested amendments
4. Emails Legal and Infosec teams immediately with pending flag counts and a dashboard link
5. Review flags in the dashboard — Accept posts a comment + highlight on the Google Doc and emails the relevant team
6. When all flags are reviewed, Legal gets a final "all reviewed" email


# Run
uvicorn server:app --port 8000



