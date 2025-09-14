"""Backend package public interface.

Expose the :mod:`backend.config` module under ``config_module`` while also
providing the instantiated configuration object as ``config``. This allows
consumers to access configuration both via ``backend.config`` (object) and the
full configuration module via ``backend.config_module``.
"""

from . import config as config_module

# Re-export the configuration instance for convenient access
config = config_module.config

__all__ = ["config", "config_module"]

