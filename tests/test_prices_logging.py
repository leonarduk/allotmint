import sys
import logging


def test_prices_import_does_not_configure_root_logger():
    root_logger = logging.getLogger()
    original_level = root_logger.level
    root_logger.setLevel(logging.WARNING)

    sys.modules.pop("backend.common.prices", None)
    import backend.common.prices  # noqa: F401

    assert root_logger.level == logging.WARNING
    root_logger.setLevel(original_level)
