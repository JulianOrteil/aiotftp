# -*- coding: utf-8 -*-

"""Utilities related to file operations."""


import os
from io import TextIOWrapper
from pathlib import Path


def ensure_path(path: str):
    path = os.fsdecode(path).lstrip('./')
    abspath = Path.cwd() / path

    try:
        abspath.relative_to(Path.cwd())
    except ValueError:
        raise FileNotFoundError(f"path '{path}' is not in the current working directory")

    if abspath.is_reserved():
        raise FileNotFoundError(f"cannot access reserved file at path '{path}'")

    return abspath


class BaseFileIO:

    _file: TextIOWrapper
    _path: Path
    _chunk_size: int
    _finished: bool

    def __init__(self, path: str, chunk_size=0) -> None:
        self._path = ensure_path(path)
        self._chunk_size = chunk_size
        self._finished = False
        self._file = self._open()

    def __del__(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()

    def _open(self) -> TextIOWrapper:
        raise NotImplementedError

    def file_size(self) -> int:
        return self._path.stat().st_size


class FileReader(BaseFileIO):

    def _open(self) -> TextIOWrapper:
        return self._path.open('rb')

    def read(self, size: int = 0) -> str:
        size = size or self._chunk_size
        if self._finished:
            raise IOError("handle has been closed")

        data = self._file.read(size)

        if not data or (size > 0 and len(data) < size):
            self.__del__()
            self._finished = True

        return data


class FileWriter(BaseFileIO):

    def _open(self) -> TextIOWrapper:
        return self._path.open('xb')

    def _flush(self) -> None:
        if self._file:
            self._file.flush()

    def write(self, data: str) -> int:
        bytes_written = self._file.write(data)

        if not data or len(data) < self._chunk_size:
            self._file.close()

        return bytes_written
