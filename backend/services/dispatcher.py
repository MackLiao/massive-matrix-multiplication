import asyncio
import logging
import struct
import time
import uuid

import numpy as np

from .protocol import (
    REQ_HDR_FMT, REQ_HDR_SIZE,
    RESP_HDR_FMT, RESP_HDR_SIZE,
    ERR_HDR_FMT, ERR_HDR_SIZE,
    STATUS_OK, FLAG_RETURN_FULL,
    pack_request,
)

logger = logging.getLogger(__name__)


def to_fixed16(matrix: np.ndarray, frac_bits: int) -> np.ndarray:
    """Convert a float matrix to int16 fixed-point (Q-format).

    Integers pass through; floats are scaled by 2**frac_bits and clipped
    to the int16 range.
    """
    if np.issubdtype(matrix.dtype, np.integer):
        return matrix.astype(np.int16)
    scale = 1 << frac_bits
    return np.clip(
        np.round(matrix * scale), -32768, 32767
    ).astype(np.int16)


async def dispatch_tile(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    a_tile: np.ndarray,
    b_tile: np.ndarray,
    frac_bits: int = 9,
    timeout: int = 60,
) -> tuple[np.ndarray, dict]:
    """Send two tiles to the FPGA over TCP and return the result.

    Uses the binary wire protocol: 32-byte request header + raw int16
    matrix bytes, receives 37-byte response header + raw float32 result.

    Returns (result_matrix, timings_dict).
    """
    request_id = uuid.uuid4().bytes  # 16 raw bytes

    # --- Client serialization ---
    t_ser_start = time.time()
    a_i16 = to_fixed16(a_tile, frac_bits)
    b_i16 = to_fixed16(b_tile, frac_bits)
    M, K = a_i16.shape
    _, N = b_i16.shape

    header = pack_request(request_id, M, K, N, frac_bits, FLAG_RETURN_FULL)
    a_bytes = a_i16.tobytes()
    b_bytes = b_i16.tobytes()
    client_serialization_sec = time.time() - t_ser_start

    # --- Network send + receive ---
    t_network_start = time.time()

    writer.write(header + a_bytes + b_bytes)
    await asyncio.wait_for(writer.drain(), timeout=timeout)

    # Read response header (first 17 bytes to check status)
    resp_prefix = await asyncio.wait_for(
        reader.readexactly(17), timeout=timeout
    )
    resp_request_id = resp_prefix[:16]
    status = resp_prefix[16]

    if status != STATUS_OK:
        # Error response: read error_len (2 bytes) then message
        err_len_bytes = await asyncio.wait_for(
            reader.readexactly(2), timeout=timeout
        )
        err_len = struct.unpack("!H", err_len_bytes)[0]
        err_msg = (await asyncio.wait_for(
            reader.readexactly(err_len), timeout=timeout
        )).decode("utf-8")
        raise RuntimeError(f"FPGA returned error: {err_msg}")

    # Success: read remaining 20 bytes of header (M, N, compute_us, deser_us, ser_us)
    resp_rest = await asyncio.wait_for(
        reader.readexactly(RESP_HDR_SIZE - 17), timeout=timeout
    )
    resp_M, resp_N, compute_us, deser_us, ser_us = struct.unpack(
        "!IIIII", resp_rest
    )

    # Read result body
    body_size = resp_M * resp_N * 4  # float32
    body = await asyncio.wait_for(
        reader.readexactly(body_size), timeout=timeout
    )
    network_round_trip_sec = time.time() - t_network_start

    # --- Client deserialization ---
    t_deser_start = time.time()
    tile_result = np.frombuffer(body, dtype=np.float32).reshape(
        resp_M, resp_N
    ).astype(np.float64)
    client_deserialization_sec = time.time() - t_deser_start

    timings = {
        "client_serialization_sec": round(client_serialization_sec, 6),
        "network_round_trip_sec": round(network_round_trip_sec, 6),
        "client_deserialization_sec": round(client_deserialization_sec, 6),
        "board_deserialization_sec": round(deser_us / 1_000_000, 6),
        "board_computation_sec": round(compute_us / 1_000_000, 6),
        "board_serialization_sec": round(ser_us / 1_000_000, 6),
    }
    return tile_result, timings
