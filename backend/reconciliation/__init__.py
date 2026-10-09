"""Statement reconciliation: read a broker document and match it against the ledger (#10474).

``extract`` turns a PDF/CSV statement into validated rows (one LLM call),
``match`` compares them deterministically with the stored transactions, and
``explain`` optionally asks the chat agent why rows are still unmatched.
Nothing here writes to the ledger; accepted suggestions go through the
existing ``/transactions`` endpoints.
"""
