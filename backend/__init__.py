"""Backend package public interface.

Expose the :mod:`backend.config` module under ``config_module`` and make it
directly available as ``config`` for convenience. Configuration values can be
accessed as attributes on this module and the underlying dataclass instance is
available as ``config.settings``.
"""

from . import config as config_module

# Re-export the configuration module so ``from backend import config`` works
# consistently in both application code and tests.
config = config_module

__all__ = ["config", "config_module"]

