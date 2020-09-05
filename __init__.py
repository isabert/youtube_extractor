# -*- coding: utf-8 -*-
"""
Export package API for the python script
"""

from __future__ import print_function, unicode_literals
from .__main__ import (
    DLvidu,                 # class
)
from .utils import (
    logger,                 # data
    logging_console_handler,
    set_logging,            # method
    get_logginglevel,
)


prog_version = "0.loo"      # used in cli only


# package export main pkg api for 'from <pkg> import *'
__all__ = [
    # __init__
    'prog_version',
    # __main__
    'DLvidu',
    # utils
    'logger', 'logging_console_handler', 'set_logging', 'get_logginglevel',
]

