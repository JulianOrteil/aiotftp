# -*- coding: utf-8 -*-

"""Async protocols for sending and receiving data."""


import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional, Tuple, Union

from loguru import logger

from .iofile import FileReader, FileWriter
from .packets import (
    TFTPAckPacket,
    TFTPDatPacket,
    TFTPErrPacket,
    TFTPOckPacket,
    TFTPPacketFactory,
    TFTPRequestPacket
)
from .utils import ensure_blksize, ensure_timeout, ensure_tsize, ensure_windowsize


class BaseProtocolFactory(asyncio.DatagramProtocol):

    @dataclass
    class DefaultOptions:
        timeout: float = 0.5
        connection_timeout: float = 5.0
        blksize: int = 512
        windowsize: int = 1

    @dataclass
    class SupportedOptions:
        blksize: Callable[..., Any] = ensure_blksize
        timeout: Callable[..., Any] = ensure_timeout
        tsize: Callable[..., Any] = ensure_tsize
        windowsize: Callable[..., Any] = ensure_windowsize

    _default_options: DefaultOptions
    _supported_options: SupportedOptions
    _packet_factory: TFTPPacketFactory

    _packet: Union[TFTPAckPacket, TFTPDatPacket, TFTPErrPacket, TFTPOckPacket, TFTPRequestPacket]
    _file_handler: Union[FileReader, FileWriter]

    _transport: asyncio.transports.DatagramTransport

    def __init__(self, packet: bytes, file_handler: Union[FileReader, FileWriter], remote_addr, options) -> None:
        super().__init__()

        self._default_options = self.DefaultOptions()
        self._supported_options = self.SupportedOptions()
        self._packet_factory = TFTPPacketFactory(
            asdict(self._default_options),
            asdict(self._supported_options)
        )

        self._packet = self._packet_factory.decode(packet)
        self._file_handler = file_handler

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:
        self._transport = transport

        self._start_communication()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        return super().connection_lost(exc)

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        raise NotImplementedError

    def error_received(self, exc: Exception) -> None:
        return super().error_received(exc)

    def _start_communication(self) -> None:
        raise NotImplementedError


class RRQProtocolFactory(BaseProtocolFactory):

    def __init__(self, packet: bytes, file_handler: object, remote_addr, options) -> None:
        super().__init__(packet, file_handler, remote_addr, options)


class WRQProtocolFactory(BaseProtocolFactory):
    pass


class BaseTFTPModeFactory(asyncio.DatagramProtocol):

    _host: str
    _loop: asyncio.ProactorEventLoop
    _kwargs: Dict[str, Any]
    _packet_factory: TFTPPacketFactory

    _transport: asyncio.transports.DatagramTransport

    def __init__(
        self,
        host: str,
        loop: asyncio.ProactorEventLoop,
        **kwargs: Dict[str, Any]
    ) -> None:
        self._host = host
        self._loop = loop
        self._kwargs = kwargs
        self._packet_factory = TFTPPacketFactory()

    def get_protocol(
        self,
        packet: TFTPRequestPacket
    ) -> Union[RRQProtocolFactory, WRQProtocolFactory]:
        raise NotImplementedError

    def get_file_handler(
        self,
        packet: TFTPRequestPacket
    ) -> Callable[..., Union[FileReader, FileWriter]]:
        raise NotImplementedError

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:
        logger.info("Waiting for a connection")

        self._transport = transport

    def connection_lost(self, exc: Optional[Exception] = None) -> None:
        logger.info("Connection lost")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        raise NotImplementedError


class TFTPClientFactory(BaseTFTPModeFactory):

    def get_protocol(self, request) -> Union[RRQProtocolFactory, WRQProtocolFactory]:
        return super().get_protocol(request)

    def get_file_handler(
        self,
        packet: TFTPRequestPacket
    ) -> Callable[..., Union[FileReader, FileWriter]]:
        pass

class TFTPServerFactory(BaseTFTPModeFactory):

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        packet = self._packet_factory.decode(data)
        protocol = self.get_protocol(packet)
        file_handler = self.get_file_handler(packet)

        io_endpoint = self._loop.create_datagram_endpoint(
            lambda: protocol(data, file_handler, addr, self._kwargs),
            (self._host, 0)
        )

        self._loop.create_task(io_endpoint)

    def get_protocol(
        self,
        packet: TFTPRequestPacket
    ) -> Union[RRQProtocolFactory, WRQProtocolFactory]:
        if packet.is_rrq():
           return RRQProtocolFactory
        elif packet.is_wrq():
            return WRQProtocolFactory
        else:
            raise ValueError("unknown client request")

    def get_file_handler(
        self,
        packet: TFTPRequestPacket
    ) -> Callable[..., Union[FileReader, FileWriter]]:
        if packet.is_rrq():
            return lambda path, options: FileReader(
                path, options
            )
        else:
            return lambda path, options: FileWriter(
                path, options
            )
