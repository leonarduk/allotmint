"""Plan-drift brief (#10475): checks the portfolio against the owner's investment plan.

* :mod:`.drift` -- deterministic facts (drift, cash, stale evidence, review, changes)
* :mod:`.prompt` -- the agent prompt and the no-advice output checks
* :mod:`.agent` -- the read-only LLM step for review triggers, assumptions and prose
* :mod:`.store` -- saved briefs per owner
* :mod:`.service` -- builds, checks and saves one brief

The brief reports facts and arithmetic only; it never recommends a trade.
"""
