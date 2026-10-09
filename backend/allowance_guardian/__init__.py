"""Contribution and allowance guardian (#10479).

Checks that scheduled pension and ISA contributions arrived, and projects the
pension annual allowance (with carry-forward) and the ISA allowance to the UK tax
year end. Facts and arithmetic only; read-only. :func:`run` is the single entry
point, ready to be registered with the bot registry (#10477) once it exists.
"""

from backend.allowance_guardian.report import ADVISER_NOTE, NOT_MODELLED, run

__all__ = ["ADVISER_NOTE", "NOT_MODELLED", "run"]
