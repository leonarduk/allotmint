"""Fund data upkeep bot (#10482).

Keeps the look-through (#9974) and fund-charges (#7834) data current and adds
what they leave out:

* :mod:`.all_in_cost` -- fund ongoing charges plus the dealing fees and
  account charges actually paid over the last 12 months, per account and in
  total, with unknown cost kept apart from zero;
* :mod:`.concentration` -- factual single-stock/country/sector exposure alerts
  on top of :func:`backend.common.look_through.compute_look_through`;
* :mod:`.charges_agent` -- an LLM agent with read-only tools that *proposes*
  missing or stale ongoing charges from public issuer documents;
* :mod:`.look_through_upkeep` -- the scheduled refresh of stale look-through
  blocks for held funds;
* :mod:`.proposals` -- the review queue; only an owner's approval writes, via
  the instrument-metadata admin path, with an audit entry that can be undone.

:func:`.bot.run` is the entry point a scheduler (the #10477 bot registry, once
it exists) calls.
"""
