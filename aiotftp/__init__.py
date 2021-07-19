# -*- coding: utf-8 -*-

"""Asynchronous TFTP file transferring."""


__all__ = ['main']

__author__ = "Julian_Orteil"
__copyright__ = "Copyright 2021, Julian_Orteil"
__license__ = "MIT"
__version__ = "0.0.1-dev"
__maintainer__ = "Julian_Orteil"
__status__ = "Development"


import asyncio
import sys

from loguru import logger

from . import utils


def main() -> int:
    """Entry point of the library when running `python -m aiotftp`.

    Returns:
        errcode (`int`):
            A non-zero return indicates an error.
    """

    # First, parse the cli args
    args = utils.parse_cli()

    # Setup logging
    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level='DEBUG')

    # Create the asyncio event loop
    loop = asyncio.get_event_loop()

    # Create the server or client
    if args.mode == utils.TFTP_MODE_CLIENT:
        logger.info("Starting aiotftp in a client configuration")
        endpoint = loop.create_datagram_endpoint(
            lambda: None,
            (args.server, args.port)
        )
    else:
        logger.info("Starting aiotftp in a server configuration")
        endpoint = loop.create_datagram_endpoint(
            lambda: None,
            (args.host, args.port)
        )

    # Submit endpoint creation
    transport, protocol = loop.run_until_complete(endpoint)

    # Execute
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.warning("Shutting down aiotftp")
    finally:
        transport.close()
        loop.close()

    logger.info("aiotftp successfully shut down")

    # Return success to the OS
    return 0
