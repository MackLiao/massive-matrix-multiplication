"""Binary wire protocol constants and helpers for FPGA board communication.

Wire format defined in docs/superpowers/specs/2026-04-03-binary-wire-protocol-design.md
"""

import struct

# ---------------------------------------------------------------------------
# Header format strings (network byte order)
# ---------------------------------------------------------------------------

# Request: request_id(16B) M(u32) K(u32) N(u32) frac_bits(u16) flags(u16)
REQ_HDR_FMT = "!16sIIIHH"
REQ_HDR_SIZE = struct.calcsize(REQ_HDR_FMT)  # 32

# Success response: request_id(16B) status(u8) M(u32) N(u32)
#                   compute_us(u32) deser_us(u32) ser_us(u32)
RESP_HDR_FMT = "!16sBIIIII"
RESP_HDR_SIZE = struct.calcsize(RESP_HDR_FMT)  # 37

# Error response prefix: request_id(16B) status(u8) error_len(u16)
ERR_HDR_FMT = "!16sBH"
ERR_HDR_SIZE = struct.calcsize(ERR_HDR_FMT)  # 19

# Status codes
STATUS_OK = 0
STATUS_ERROR = 1

# Flag bits
FLAG_RETURN_FULL = 1  # bit 0: return full result matrix


# ---------------------------------------------------------------------------
# Pack / unpack helpers
# ---------------------------------------------------------------------------

def pack_request(request_id: bytes, M: int, K: int, N: int,
                 frac_bits: int, flags: int = FLAG_RETURN_FULL) -> bytes:
    """Pack a 32-byte request header."""
    return struct.pack(REQ_HDR_FMT, request_id, M, K, N, frac_bits, flags)


def unpack_request(header: bytes) -> tuple:
    """Unpack a 32-byte request header.

    Returns (request_id, M, K, N, frac_bits, flags).
    """
    return struct.unpack(REQ_HDR_FMT, header)


def pack_response(request_id: bytes, M: int, N: int,
                  compute_us: int, deser_us: int, ser_us: int) -> bytes:
    """Pack a 37-byte success response header."""
    return struct.pack(RESP_HDR_FMT, request_id, STATUS_OK,
                       M, N, compute_us, deser_us, ser_us)


def unpack_response(header: bytes) -> tuple:
    """Unpack a 37-byte response header.

    Returns (request_id, status, M, N, compute_us, deser_us, ser_us).
    """
    return struct.unpack(RESP_HDR_FMT, header)


def pack_error(request_id: bytes, message: str) -> bytes:
    """Pack an error response (header + message body)."""
    msg_bytes = message.encode("utf-8")
    header = struct.pack(ERR_HDR_FMT, request_id, STATUS_ERROR, len(msg_bytes))
    return header + msg_bytes


def recv_exact(sock, n: int) -> bytes:
    """Read exactly *n* bytes from a blocking socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while reading")
        buf.extend(chunk)
    return bytes(buf)
