"""Top-level package for moat.gpio."""

import sys

from .gpio import Chip, Event, Line  # noqa: F401
from .libgpiod import *  # noqa


def open_chip(num=None, label=None, consumer=sys.argv[0]):
    """Returns an object representing a GPIO chip.

    Arguments:
        num: Chip number. Defaults to zero.

        consumer: A string for display by kernel utilities.
            Defaults to the program's name.

    Returns:
        a :class:`moat.gpio.gpio.Chip` instance.
    """
    return Chip(num=num, label=label, consumer=consumer)
