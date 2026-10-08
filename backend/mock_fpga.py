"""Mock FPGA TCP server for development.

Implements the binary wire protocol, simulating the PYNQ board's
matrix multiplication accelerator with numpy.

Usage:
    python -m backend.mock_fpga [--port 5000] [--delay 0.5]
"""

import argparse
import asyncio
import logging
import os
import struct
import time

import numpy as np

from backend.services.protocol import (
    REQ_HDR_FMT, REQ_HDR_SIZE,
    RESP_HDR_FMT, RESP_HDR_SIZE,
    STATUS_OK, STATUS_ERROR,
    ERR_HDR_FMT,
    pack_response, pack_error,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mock_fpga")

DELAY = float(os.environ.get("MOCK_FPGA_DELAY", "0.5"))
FRAC_BITS = int(os.environ.get("MOCK_FRAC_BITS", "9"))

# Match real board hardware constraints
TILE_ROWS = 8
TILE_COLS = 8
TILE_DEPTH = 128
MAX_DIM = 2048


async def handle_connection(reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
    peer = writer.get_extra_info("peername")
    logger.info(f"Connection from {peer}")

    try:
        while True:
            # Read 32-byte request header
            try:
                raw_header = await reader.readexactly(REQ_HDR_SIZE)
            except (asyncio.IncompleteReadError, ConnectionError):
                break

            request_id, M, K, N, frac_bits, flags = struct.unpack(
                REQ_HDR_FMT, raw_header
            )

            # Health check: M == 0
            if M == 0:
                logger.info(f"[{request_id.hex()[:8]}] Health check")
                header = struct.pack(
                    RESP_HDR_FMT, request_id, STATUS_OK,
                    TILE_ROWS, TILE_COLS, TILE_DEPTH, frac_bits, MAX_DIM,
                )
                writer.write(header)
                await writer.drain()
                continue

            rid_short = request_id.hex()[:8]
            logger.info(f"[{rid_short}] Multiply {M}x{K} @ {K}x{N}")

            # Validate dimensions
            if M % TILE_ROWS != 0:
                writer.write(pack_error(request_id,
                             f"Rows ({M}) must be divisible by {TILE_ROWS}"))
                await writer.drain()
                continue
            if N % TILE_COLS != 0:
                writer.write(pack_error(request_id,
                             f"Cols ({N}) must be divisible by {TILE_COLS}"))
                await writer.drain()
                continue
            if K % TILE_DEPTH != 0:
                writer.write(pack_error(request_id,
                             f"Inner dim ({K}) must be divisible by {TILE_DEPTH}"))
                await writer.drain()
                continue

            # Read matrix data
            t_deser_start = time.time()
            a_bytes = await reader.readexactly(M * K * 2)
            b_bytes = await reader.readexactly(K * N * 2)
            mat_a = np.frombuffer(a_bytes, dtype=np.int16).reshape(M, K)
            mat_b = np.frombuffer(b_bytes, dtype=np.int16).reshape(K, N)
            deser_us = int((time.time() - t_deser_start) * 1_000_000)

            # Simulate compute delay
            if DELAY > 0:
                await asyncio.sleep(DELAY)

            t_compute_start = time.time()
            # Simulate fixed-point MAC: int16 * int16 -> int64 accumulator
            fb = frac_bits if frac_bits > 0 else FRAC_BITS
            raw = mat_a.astype(np.int64) @ mat_b.astype(np.int64)
            result = raw.astype(np.float32) / (1 << (2 * fb))
            compute_us = int((time.time() - t_compute_start) * 1_000_000)

            # Send response
            t_ser_start = time.time()
            resp_M, resp_N = result.shape
            header = pack_response(request_id, resp_M, resp_N,
                                   compute_us, deser_us, 0)
            body = result.astype(np.float32).tobytes()
            writer.write(header + body)
            await writer.drain()
            ser_us = int((time.time() - t_ser_start) * 1_000_000)

            logger.info(f"[{rid_short}] Done — compute={compute_us}us "
                        f"deser={deser_us}us ser={ser_us}us")

    except Exception:
        logger.exception(f"Error handling connection from {peer}")
    finally:
        writer.close()
        await writer.wait_closed()
        logger.info(f"Connection from {peer} closed")


async def main(port: int):
    server = await asyncio.start_server(handle_connection, "0.0.0.0", port)
    addr = server.sockets[0].getsockname()
    logger.info(f"Mock FPGA TCP server listening on {addr[0]}:{addr[1]}")
    logger.info(f"Delay={DELAY}s, frac_bits={FRAC_BITS}")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mock FPGA TCP server")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--delay", type=float, default=None,
                        help="Override MOCK_FPGA_DELAY")
    args = parser.parse_args()
    if args.delay is not None:
        DELAY = args.delay
    asyncio.run(main(args.port))
