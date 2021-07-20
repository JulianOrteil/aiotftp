# -*- coding: utf-8 -*-

"""NETASCII transfer encoding helpers."""


import os
import re
from io import TextIOWrapper
from typing import Callable, Dict


CR = b'\x0d'
LF = b'\x0a'
CRLF = CR + LF
NUL = b'\x00'
CRNUL = CR + NUL
NL = os.linesep if isinstance(os.linesep, bytes) else os.linesep.encode('ascii')


def _replace(mapping: Dict[bytes, bytes]) -> Callable[[bytes], bytes]:
    pattern = re.compile(b'|'.join(map(re.escape, mapping)))

    @staticmethod
    def wrapper(data: bytes) -> bytes:
        return pattern.sub(lambda match: mapping[match.group(0)], data)

    return wrapper


class NETASCII:
    from_netascii = _replace({CRLF: NL, CRNUL: CR})
    to_netascii = _replace({NL: CRLF, CR: CRNUL})

    _buffer: bytes
    _file_handle: TextIOWrapper

    def __init__(self, file_handler: TextIOWrapper) -> None:
        self._file_handle = file_handler
        self._buffer = b''

    def read(self, size) -> bytes:
        buffer_size = 0
        if self._buffer:
            buffer_size = len(self._buffer)
        data = self._buffer + self.to_netascii(self._file_handle.read(size - buffer_size))
        self._buffer = data[size:]

        return data[:size]

    def write(self, data) -> None:
        if self._buffer:
            data = self._buffer + data
            self._buffer = b''
        if data[-1:] == CR:
            self._buffer = data[-1:]
            data = data[:-1]

        self._file_handle.write(self.from_netascii(data))

    def close(self) -> None:
        self._file_handle.close()

    def is_closed(self) -> bool:
        return self._file_handle.closed

    def flush(self) -> None:
        self._file_handle.flush()
