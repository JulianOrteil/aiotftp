# -*- coding: utf-8 -*-

"""TFTP packet helpers."""


from __future__ import annotations


from typing import Any, Dict, NamedTuple, Optional, Union

from . import utils


class TFTPPacketFactory:

    _default_options: Dict[str, Any]
    _supported_options: Dict[str, Any]

    def __init__(
        self,
        default_options: Dict[str, Any] = {},
        supported_options: Dict[str, Any] = {}
    ) -> None:
        self._default_options = default_options
        self._supported_options = supported_options

    def decode(
        self,
        data: bytes
    ) -> Union[TFTPAckPacket, TFTPDatPacket, TFTPErrPacket, TFTPOckPacket, TFTPRequestPacket]:
        type_ = BaseTFTPPacket.PacketTypes.decode(data[:2])

        if type_ in {BaseTFTPPacket.PacketTypes.RRQ, BaseTFTPPacket.PacketTypes.WRQ}:
            fname, mode, options = utils.ensure_request(
                *utils.parse_request(data[2:]),
                self._supported_options,
                self._default_options
            )
            return self.create(type_, fname=fname, mode=mode, options=options)
        elif type_ == BaseTFTPPacket.PacketTypes.ACK:
            block_no = BaseTFTPPacket.unpack_short(data[2:4])
            return self.create(type_, block_no=block_no)
        elif type_ == BaseTFTPPacket.PacketTypes.DAT:
            block_no = BaseTFTPPacket.unpack_short(data[2:4])
            return self.create(type_, block_no=block_no, data=data[4:])
        elif type_ == BaseTFTPPacket.PacketTypes.ERR:
            code = BaseTFTPPacket.unpack_short(data[2:4])
            return self.create(type_, code=code, message=data[4:])
        elif type_ == BaseTFTPPacket.PacketTypes.OCK:
            _, _, options = utils.ensure_request(
                *utils.parse_request(data[2:]),
                self._supported_options,
                self._default_options
            )
            return self.create(type_, options=options)

    @classmethod
    def create(
        cls: TFTPPacketFactory,
        type: Optional[str] = None,
        **kwargs: Dict[str, Any]
    ) -> Union[TFTPAckPacket, TFTPDatPacket, TFTPErrPacket, TFTPOckPacket, TFTPRequestPacket]:
        if type in {BaseTFTPPacket.PacketTypes.RRQ, BaseTFTPPacket.PacketTypes.WRQ}:
            return TFTPRequestPacket(type, **kwargs)
        elif type == BaseTFTPPacket.PacketTypes.ACK:
            return TFTPAckPacket(**kwargs)
        elif type == BaseTFTPPacket.PacketTypes.DAT:
            return TFTPDatPacket(**kwargs)
        elif type == BaseTFTPPacket.PacketTypes.ERR:
            return TFTPErrPacket(**kwargs)
        elif type == BaseTFTPPacket.PacketTypes.OCK:
            return TFTPOckPacket(**kwargs)
        else:
            raise ValueError(f"Unknown packet type '{type}'")


class BaseTFTPPacket:

    class PacketTypes(NamedTuple):
        RRQ: str = 'RRQ'
        WRQ: str = 'WRQ'
        DAT: str = 'DAT'
        ACK: str = 'ACK'
        ERR: str = 'ERR'
        OCK: str = 'OCK'

        RRQ_code: bytes = b'\x00\x01'
        WRQ_code: bytes = b'\x00\x02'
        DAT_code: bytes = b'\x00\x03'
        ACK_code: bytes = b'\x00\x04'
        ERR_code: bytes = b'\x00\x05'
        OCK_code: bytes = b'\x00\x06'

        @classmethod
        def decode(cls, code: bytes) -> str:
            if code == cls.RRQ_code:
                return cls.RRQ
            elif code == cls.WRQ_code:
                return cls.WRQ
            elif code == cls.DAT_code:
                return cls.DAT
            elif code == cls.ACK_code:
                return cls.ACK
            elif code == cls.ERR_code:
                return cls.ERR
            elif code == cls.OCK_code:
                return cls.OCK
            else:
                raise ValueError(f"Unrecognized packet bytecode '{code}'")

        @classmethod
        def validate(cls, type: str) -> str:
            type = type.upper()

            if type == cls.RRQ:
                return cls.RRQ
            elif type == cls.WRQ:
                return cls.WRQ
            elif type == cls.DAT:
                return cls.DAT
            elif type == cls.ACK:
                return cls.ACK
            elif type == cls.ERR:
                return cls.ERR
            elif type == cls.OCK:
                return cls.OCK
            else:
                raise ValueError(f"Unrecognized packet type '{type}'")

    _type: str

    def __init__(self) -> None:
        self._type = None

    def encode(self) -> bytes:
        raise NotImplementedError

    def is_ack(self) -> bool:
        return self._type == self.PacketTypes.ACK

    def is_data(self) -> bool:
        return self._type == self.PacketTypes.DAT

    def is_err(self) -> bool:
        return self._type == self.PacketTypes.ERR

    def is_ock(self) -> bool:
        return self._type == self.PacketTypes.OCK

    def is_rrq(self) -> bool:
        return self._type == self.PacketTypes.RRQ

    def is_wrq(self) -> bool:
        return self._type == self.PacketTypes.WRQ

    def get_size(self) -> int:
        return len(self.encode())

    @classmethod
    def _to_bytes(cls, other: Any) -> bytes:
        if isinstance(other, bytes):
            return other
        else:
            return str(other).encode('ascii')

    @classmethod
    def pack_short(cls, n: int) -> bytes:
        return n.to_bytes(2, byteorder='big')

    @classmethod
    def unpack_short(cls, data: bytes) -> int:
        return int.from_bytes(data, byteorder='big')

    @classmethod
    def serialize_options(cls, options: Dict[str, Any]):
        opt_items = [val for pair in options.items() for val in pair]
        opt_items = [cls._to_bytes(val) for val in opt_items]
        return b'\x00'.join(opt_items)


class TFTPAckPacket(BaseTFTPPacket):

    _block_no: int

    def __init__(self, **kwargs: Dict[str, Any]) -> None:
        super().__init__()

        self._type = self.PacketTypes.ACK
        self._block_no = kwargs['block_no']

    def encode(self) -> bytes:
        return b''.join([self.PacketTypes.ACK, BaseTFTPPacket.pack_short(self._block_no)])


class TFTPDatPacket(BaseTFTPPacket):

    _block_no: int
    _data: str

    def __init__(self, **kwargs: Dict[str, Any]) -> None:
        super().__init__()

        self._type = self.PacketTypes.DAT
        self._block_no = kwargs['block_no']
        self._data = kwargs['data']

    def encode(self) -> bytes:
        return b''.join(
            [self.PacketTypes.DAT, BaseTFTPPacket.pack_short(self._block_no), self._data]
        )


class TFTPErrPacket(BaseTFTPPacket):

    _code: object
    _message: str

    def __init__(self, **kwargs: Dict[str, Any]) -> None:
        super().__init__()

        self._type = self.PacketTypes.ERR
        self._code = kwargs['code']
        self._message = kwargs['message']

    def encode(self) -> bytes:
        return b''.join([
            self.PacketTypes.ERR,
            BaseTFTPPacket.pack_short(self._code),
            self._message.encode('ascii'),
            b'\x00'
        ])


class TFTPOckPacket(BaseTFTPPacket):

    _options: Dict[str, Any]

    def __init__(self, **kwargs: Dict[str, Any]) -> None:
        super().__init__()

        self._type = self.PacketTypes.OCK
        self._options = kwargs.get('options', {})

    def encode(self) -> bytes:
        return b''.join([
            self.PacketTypes.OCK,
            BaseTFTPPacket.serialize_options(self._options),
            b'\x00'
        ])


class TFTPRequestPacket(BaseTFTPPacket):

    _fname: bytes
    _mode: bytes
    _options: bytes

    def __init__(
        self,
        type: str,
        **kwargs: Dict[str, Any]
    ) -> None:
        super().__init__()

        self._type = type
        self._fname = kwargs['fname']
        self._mode = kwargs['mode']
        self._options = kwargs.get('options', {})

    def encode(self) -> bytes:
        packet = [
            self.PacketTypes.validate(self._type) + bytes(self._fname, 'ascii'),
            bytes(self._mode, 'ascii'),
            BaseTFTPPacket.serialize_options(self._options)
        ]
        return b'\x00'.join([part for part in packet if part]) + b'\x00'
