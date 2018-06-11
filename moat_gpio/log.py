# -*- coding: utf-8 -*-

"""Module for setting up logging."""

import logging
import sys

LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}

LOG_FORMATS = {
    'DEBUG': u'%(levelname)s %(name)s: %(message)s',
    'INFO': u'%(levelname)s: %(message)s',
}


def configure_logger(stream_level='DEBUG'):
    """Configure logging for MoaT-GPIO.

    Set up logging to stdout with given level. If ``debug_file`` is given set
    up logging to file with DEBUG level.
    """
    # Set up 'cookiecutter' logger
    logger = logging.getLogger('moat-gpio')
    logger.setLevel(logging.DEBUG)

    del logger.handlers[:]

    # Get settings based on the given stream_level
    log_formatter = logging.Formatter(LOG_FORMATS[stream_level])
    log_level = LOG_LEVELS[stream_level]

    # Create a stream handler
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)

    return logger
