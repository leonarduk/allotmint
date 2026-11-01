"""Decision journal (#10481): log owner decisions with their context and review them later.

* :mod:`.capture` finds qualifying changes (trades above a threshold, plan
  target edits) and pre-fills the facts and a context snapshot. It never
  writes; the owner writes the reasoning and confirms.
* :mod:`.store` keeps the sidecar record (snapshot, legs, expectation,
  reviews) linked to the plan's ``decisions`` entry by ``id``.
* :mod:`.review` builds the 6- and 12-month counterfactual against the
  alternatives the owner listed, labelled with its return basis.
* :mod:`.patterns` counts how the option taken ended against each kind of
  alternative across reviewed entries, split by return basis (#10489).
* :mod:`.bot` is the daily run: list unlogged changes and run due reviews.
"""
