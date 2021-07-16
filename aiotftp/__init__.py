# -*- coding: utf-8 -*-

"""Asynchronous TFTP file transferring."""


__all__ = ['main']

__author__ = "Julian_Orteil"
__copyright__ = "Copyright 2021, Julian_Orteil"
__license__ = "MIT"
__version__ = "0.0.1-dev"
__maintainer__ = "Julian_Orteil"
__status__ = "Development"


from . import utils


def main() -> int:
    """Entry point of the library when running `python -m aiotftp`.

    Returns:
        errcode (`int`):
            A non-zero return indicates an error.
    """

    # First, parse the cli args
    args = utils.parse_cli()

    # Return success to the OS
    return 0
