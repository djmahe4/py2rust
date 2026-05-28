from __future__ import annotations
import logging
import sys

_logger = logging.getLogger("py2rust")


def setup_logger(verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    fmt = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(fmt)
    _logger.setLevel(level)
    _logger.handlers.clear()
    _logger.addHandler(handler)
    return _logger


def get_logger() -> logging.Logger:
    return _logger
