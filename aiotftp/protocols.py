# -*- coding: utf-8 -*-

"""Async protocols for sending and receiving data."""


import asyncio
from dataclasses import asdict, dataclass
from io import TextIOWrapper
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

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
    _packets: List[Union[TFTPAckPacket, TFTPDatPacket, TFTPErrPacket, TFTPOckPacket, TFTPRequestPacket, None]]
    _file_handler_cls: Union[FileReader, FileWriter]
    _remote_addr: Tuple[str, int]
    _extra_options: Dict[str, Any]

    _transport: asyncio.transports.DatagramTransport

    _counter: int
    _r_options: Dict[str, Any]
    _options: Dict[str, Any]
    _retransmitter: asyncio.TimerHandle
    _retransmitters: List[asyncio.TimerHandle]
    _connection_timeout_timer: asyncio.TimerHandle
    _file_handler: TextIOWrapper

    def __init__(
        self,
        packet: bytes,
        file_handler_cls: Union[FileReader, FileWriter],
        remote_addr: Tuple[str, int],
        options: Dict[str, Any] = {}
    ) -> None:
        super().__init__()

        self._default_options = self.DefaultOptions()
        self._supported_options = self.SupportedOptions()
        self._packet_factory = TFTPPacketFactory(
            asdict(self._default_options),
            asdict(self._supported_options)
        )

        self._packet = self._packet_factory.decode(packet)
        self._file_handler_cls = file_handler_cls
        self._remote_addr = remote_addr
        self._extra_options = options

        self._counter = 0
        self._r_options = {}
        self._options = {}
        self._retransmitter = None
        self._retransmitters = []
        self._connection_timeout_timer = None
        self._file_handler = None

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:
        logger.info(f"New connection made from '{self._remote_addr[0]}:{self._remote_addr[1]}'")
        self._transport = transport

        self._start_communication()

    def connection_lost(self, exc: Optional[Exception]) -> None:
        logger.info(f"Connection from '{self._remote_addr[0]}:{self._remote_addr[1]}' lost")
        self.reset_connection()

    def connection_timed_out(self) -> None:
        self.reset_retransmitters()
        self._transport.close()

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        raise NotImplementedError

    def error_received(self, exc: Exception) -> None:
        self.reset_connection()
        self._transport.close()

    def is_correct_tid(self, addr: Tuple[str, int]) -> bool:
        if self._remote_addr[1] == addr[1]:
            return True
        else:
            packet = self._packet_factory.create_err_unknown_tid()
            self._transport.sendto(packet.encode(), addr)
            return False

    def reset_connection(self) -> None:
        self.reset_retransmitters()
        if self._connection_timeout_timer:
            self._connection_timeout_timer.cancel()

    def _reset_connection_timeout(self) -> None:
        self.reset_connection()
        self._connection_timeout_timer = asyncio.get_event_loop().call_later(
            self._default_options.connection_timeout, self.connection_timed_out
        )

    def reset_retransmitters(self) -> None:
        if self._default_options.windowsize > 1:
            for retransmit_loop in self._retransmitters:
                retransmit_loop.cancel()
            self._retransmitters = []
        else:
            if self._retransmitter:
                self._retransmitter.cancel()

    def _next_datagram(self) -> TFTPDatPacket:
        raise NotImplementedError

    def _open_file_handler(self) -> None:
        raise NotImplementedError

    def _set_protocol_attrs(self) -> None:
        self._filename = self._packet._fname
        self._r_options = self._packet._options
        self._options = {**asdict(self._default_options), **self._extra_options, **self._r_options}

    def _start_communication(self) -> None:
        try:

            self._set_protocol_attrs()
            self._open_file_handler()

            if self._r_options:
                self._counter = 0
                packet = self._packet_factory.create(
                    TFTPOckPacket.PacketTypes.OCK,
                    options=self._r_options
                )
            else:
                packet = self._next_datagram()
        except FileExistsError:
            logger.warning(f"Cannot overwrite file '{self._filename}'")
            packet = self._packet_factory.create_err_file_exists()
        except FileNotFoundError:
            logger.warning(f"No such file '{self._filename}' exists")
            packet = self._packet_factory.create_err_file_404()
        except PermissionError:
            logger.warning(f"Insufficient permissions to operate on file '{self._filename}'")
            packet = self._packet_factory.create_err_access_violation()

        self._start_transmission(packet.encode())
        if packet.is_err():
            # TODO: Handle
            pass

    def _start_transmission(self, packet: bytes) -> None:
        self._send_packet(packet)
        self._connection_timeout_timer = asyncio.get_event_loop().call_later(
            self._default_options.connection_timeout, self.reset_connection
        )

    def _send_packet(self, packet: bytes) -> None:
        self._transport.sendto(packet, self._remote_addr)
        self._retransmitter = asyncio.get_event_loop().call_at(
            self._default_options.timeout, self._send_packet, packet
        )
        if self._default_options.windowsize > 1:
            self._retransmitters.append(self._retransmitter)


class RRQProtocolFactory(BaseProtocolFactory):

    def __init__(
        self,
        packet: bytes,
        file_handler_cls: Union[FileReader, FileWriter],
        remote_addr: str,
        options: Dict[str, Any]
    ) -> None:
        super().__init__(packet, file_handler_cls, remote_addr, options)

    def _open_file_handler(self) -> None:
        self._counter = 1
        self._file_handler = self._file_handler_cls(self._filename, self._default_options.blksize)

        if 'tsize' in self._r_options:
            self._r_options = self._file_handler.file_size()
        if self._default_options.windowsize > 1:
            self._packets = [None] * self._default_options.windowsize

    def _datagram_received_default(self, data: bytes, addr: Tuple[str, int]) -> None:
        packet = self._packet_factory.decode(data)
        if self.is_correct_tid(addr) and packet.is_err():
            # TODO: Handle packet error
            return None
        if (
            self.is_correct_tid(addr)
            and packet.is_ack()
            and packet.is_correct_sequence(self._counter)
        ):
            self._reset_connection_timeout()
            if self._file_handler._finished:
                self._transport.close()
                return None
            self._counter = (self._counter + 1) % 65536
            packet = self._next_datagram()
            self._send_packet(packet.encode())
        else:
            # Verbose output of status
            return None
        return None

    def _datagram_received_windowsize(
        self,
        data: bytes,
        addr: Tuple[str, int],
        windowsize: int
    ) -> None:
        packet = self._packet_factory.decode(data)
        if self.is_correct_tid(addr) and packet.is_err():
            # TODO: Handle packet error
            return None
        if self.is_correct_tid(addr) and packet.is_ack() and self._is_packet_in_windowsize(packet, windowsize):
            self._reset_connection_timeout()
            if packet.is_correct_sequence(self._counter):
                if self._file_handler._finished:
                    self._transport.close()
                    return None
                next_packet_id = windowsize
            else:
                counter_diff = self._counter - packet._block_no
                next_packet_id = windowsize - counter_diff
                self._counter += 1 - next_packet_id
            for i in range(next_packet_id):
                if self._file_handler._finished:
                    self._packet = self._packets[-i:]
                    break

                self._packets.pop(0)
                self._counter = (self._counter + 1) % 65536
                packet = self._next_datagram()
                self._packets.append(packet)
            for packet in self._packets:
                self._send_packet(packet.encode())
        else:
            # Verbose output of status
            return None
        return None

    def _is_packet_in_windowsize(self, packet: TFTPDatPacket, windowsize: int) -> bool:
        return packet._block_no > (self._counter - windowsize) and packet._block_no <= self._counter

    def _next_datagram(self) -> TFTPDatPacket:
        return self._packet_factory.create(
            TFTPDatPacket.PacketTypes.DAT,
            block_no=self._counter,
            data=self._file_handler.read()
        )

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        if self._default_options.windowsize > 1:
            self._datagram_received_windowsize(data, addr, self._default_options.windowsize)
        else:
            self._datagram_received_default(data, addr)


class WRQProtocolFactory(BaseProtocolFactory):

    def __init__(
        self,
        packet: bytes,
        file_handler: Union[FileReader, FileWriter],
        remote_addr: Tuple[str, int],
        options: Dict[str, Any]
    ) -> None:
        super().__init__(packet, file_handler, remote_addr, options=options)

    def _next_datagram(self) -> TFTPAckPacket:
        return self._packet_factory.create(
            type=TFTPAckPacket.PacketTypes.ACK,
            block_no=self._counter
        )

    def _open_file_handler(self) -> None:
        self._counter = 0
        self._file_handler = self._file_handler_cls(self._filename, self._default_options.blksize)

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        packet = self._packet_factory.decode(data)

        if (
            self.is_correct_tid(addr)
            and packet.is_data()
            and packet.is_correct_sequence((self._counter + 1) % 65536)
        ):
            self._reset_connection_timeout()

            self._counter = (self._counter + 1) % 65536
            reply_packet = self._next_datagram()
            self._send_packet(reply_packet.encode())

            self._file_handler.write(packet._data)

            if packet.get_size() < self._default_options.blksize:
                self.reset_retransmitters()
                self._transport.close()


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
        raise NotImplementedError

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

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:
        self._transport = transport

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
                path, options, packet._mode
            )
        else:
            return lambda path, options: FileWriter(
                path, options, packet._mode
            )
