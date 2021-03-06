# -*- coding: utf-8 -*-

"""Useful library utilities."""


import argparse
import sys
from typing import Any, Dict, Tuple

from . import __version__


TFTP_MODE_CLIENT = 'client'
TFTP_MODE_SERVER = 'server'


def parse_cli() -> argparse.Namespace:
    """Parse cli arguments."""

    # Create the parsers
    parser = argparse.ArgumentParser(
        prog='aioftp',
        description="Asynchronous TFTP file transferring"
    )
    mode_subparsers = parser.add_subparsers(
        title='TFTP mode',
        metavar=None,
        dest='mode'
    )

    # Top-level parser
    parser.add_argument('-v', '--version', action='store_true', help="print the version and exit")
    parser.add_argument('-V', '--verbose', action='store_true', help="print extra runtime information to stderr")

    # Client parser
    client_parser = mode_subparsers.add_parser(
        'client',
        help='run aiotftp as a client',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    client_parser.add_argument(
        'transfer_mode',
        choices=['GET', 'PUT'],
        help="'GET' a file from the server or 'PUT' a file to the server"
    )
    client_parser.add_argument(
        'server',
        help="the IP address of the TFTP server"
    )
    client_parser.add_argument(
        '-P',
        '--port',
        default=69,
        type=int,
        help="the port the TFTP server is listening on"
    )
    client_parser.add_argument(
        'source',
        help=(
            "the file to transfer. "
            "If 'GET', this is the file on the server; if 'PUT', this is the file locally"
        )
    )
    client_parser.add_argument(
        'destination',
        help=(
            "where to transfer the file. "
            "If 'GET', this is the dest locally; if 'PUT', this is the dest on the server"
        )
    )

    # Server parser
    server_parser = mode_subparsers.add_parser(
        'server',
        help='run aiotftp as a server',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    server_parser.add_argument(
        '-H',
        '--host',
        default='0.0.0.0',
        help="the IP address the server is listening at for connections"
    )
    server_parser.add_argument(
        '-P',
        '--port',
        default=6969,
        type=int,
        help=(
            "the port the server is listening on for connections. "
            "WARNING: *nix requires raised privileges for port 69"
        )
    )
    server_parser.add_argument(
        '--restrict_modes',
        nargs='+',
        choices=['GET', 'PUT'],
        default=['GET', 'PUT'],
        help="restrict the type of file transferring"
    )

    # Parse the args
    args = parser.parse_args()

    # HACK: Top-level mut. exclusives check
    if args.version:
        print(__version__)
        sys.exit(0)
    elif not args.mode:
        parser.print_help(sys.stderr)
        sys.exit(0)

    return args


def ensure_request(
    fname: bytes,
    mode: bytes,
    options: Dict[str, Any],
    supported_options: Dict[str, Any] = {},
    default_options: Dict[str, Any] = {}
) -> Tuple[str, bytes, Dict[str, Any]]:
    acknowledged_options = {}

    for key, value in options.items():
        if key in supported_options.keys():
            try:
                acknowledged_options[key] = supported_options[key](value)
            except ValueError:
                # TODO: Handle
                pass

    return (fname.decode(encoding='ascii'), mode, acknowledged_options)


def parse_request(data: bytes) -> Tuple[bytes, bytes, Dict[str, Any]]:
    fname, mode, *options = [item for item in data.split(b'\x00') if item]
    options = dict(zip(options[::2], options[1::2]))

    return fname, mode, options


def ensure_blksize(value: int, lower_bound=8, upper_bound=65464) -> int:
    value = int(value)

    if value > upper_bound:
        return value - (value - upper_bound)
    elif value > lower_bound:
        raise ValueError(f"blksize '{value}' lower than RFC spec limit '{lower_bound}'")
    else:
        return value


def ensure_timeout(value: float, lower_bound=1, upper_bound=255) -> float:
    value = float(value)

    if value > upper_bound or value < lower_bound:
        raise ValueError(f"timeout '{value}' lower than RFC spec limit '{lower_bound}'")
    else:
        return value


def ensure_tsize(value: int, lower_bound=0, upper_bound=None) -> int:
    return int(value)


def ensure_windowsize(value: int, lower_bound=1, upper_bound=65535) -> int:
    value = int(value)

    if value > upper_bound:
        return value - (value - upper_bound)
    elif value > lower_bound:
        raise ValueError(f"windowsize '{value}' lower than RFC spec limit '{lower_bound}'")
    else:
        return value
