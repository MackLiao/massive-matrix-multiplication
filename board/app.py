"""
TCP server for the systolic array matrix multiplication accelerator.
Runs on the PYNQ board.

Binary wire protocol replaces the previous Flask HTTP + JSON server.
See docs/superpowers/specs/2026-04-03-binary-wire-protocol-design.md

Usage:
    python3 app.py [--bitstream PATH] [--frac-bits N] [--port PORT]
"""

import argparse
import atexit
import logging
import socketserver
import struct
import time

import numpy as np

from matrixMultiplicationAccelerator import MatrixAccelerator, N_ROWS, N_COLS, TILE_DEPTH, MAX_DIM

# ---------------------------------------------------------------------------
# Protocol constants (duplicated from backend/services/protocol.py because
# the board runs standalone on the PYNQ — no shared package install)
# ---------------------------------------------------------------------------
REQ_HDR_FMT = "!16sIIIHH"
REQ_HDR_SIZE = struct.calcsize(REQ_HDR_FMT)   # 32

RESP_HDR_FMT = "!16sBIIIII"
RESP_HDR_SIZE = struct.calcsize(RESP_HDR_FMT)  # 37

ERR_HDR_FMT = "!16sBH"
ERR_HDR_SIZE = struct.calcsize(ERR_HDR_FMT)    # 19

STATUS_OK = 0
STATUS_ERROR = 1

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("board")

accel = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def recv_exact(sock, n: int) -> bytes:
    """Read exactly *n* bytes from a socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed while reading")
        buf.extend(chunk)
    return bytes(buf)


def send_error(sock, request_id: bytes, message: str):
    """Send a status=1 error response."""
    msg_bytes = message.encode("utf-8")
    header = struct.pack(ERR_HDR_FMT, request_id, STATUS_ERROR, len(msg_bytes))
    sock.sendall(header + msg_bytes)


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class TileHandler(socketserver.BaseRequestHandler):
    """Handle one TCP connection.

    A connection may carry multiple sequential requests (persistent connection).
    """

    def handle(self):
        peer = self.client_address
        logger.info(f"Connection from {peer}")

        try:
            while True:
                # Read 32-byte request header
                try:
                    raw_header = recv_exact(self.request, REQ_HDR_SIZE)
                except ConnectionError:
                    break  # client closed connection

                request_id, M, K, N, frac_bits, flags = struct.unpack(
                    REQ_HDR_FMT, raw_header
                )

                # Health check: M == 0
                if M == 0:
                    logger.info(f"[{request_id.hex()[:8]}] Health check")
                    header = struct.pack(
                        RESP_HDR_FMT, request_id, STATUS_OK,
                        N_ROWS, N_COLS, TILE_DEPTH, frac_bits, MAX_DIM,
                    )
                    self.request.sendall(header)
                    continue

                rid_short = request_id.hex()[:8]
                logger.info(f"[{rid_short}] Multiply {M}x{K} @ {K}x{N}, "
                            f"frac_bits={frac_bits}")

                # Validate dimensions
                if M > MAX_DIM or N > MAX_DIM or K > MAX_DIM:
                    send_error(self.request, request_id,
                               f"Dimensions exceed MAX_DIM={MAX_DIM}")
                    continue
                if M % N_ROWS != 0:
                    send_error(self.request, request_id,
                               f"Rows ({M}) must be divisible by {N_ROWS}")
                    continue
                if N % N_COLS != 0:
                    send_error(self.request, request_id,
                               f"Cols ({N}) must be divisible by {N_COLS}")
                    continue
                if K % TILE_DEPTH != 0:
                    send_error(self.request, request_id,
                               f"Inner dim ({K}) must be divisible by {TILE_DEPTH}")
                    continue

                # Read matrix data
                t_deser_start = time.time()
                a_bytes = recv_exact(self.request, M * K * 2)  # int16
                b_bytes = recv_exact(self.request, K * N * 2)  # int16
                mat_a = np.frombuffer(a_bytes, dtype=np.int16).reshape(M, K)
                mat_b = np.frombuffer(b_bytes, dtype=np.int16).reshape(K, N)
                deser_us = int((time.time() - t_deser_start) * 1_000_000)

                # Compute
                try:
                    t_compute_start = time.time()
                    result = accel.multiply(mat_a, mat_b)
                    compute_us = int((time.time() - t_compute_start) * 1_000_000)

                    # Scale back from fixed-point accumulators
                    scale_sq = 1 << (2 * frac_bits)
                    result = result.astype(np.float32) / scale_sq
                except Exception as e:
                    logger.exception(f"[{rid_short}] Accelerator error")
                    send_error(self.request, request_id,
                               "Internal accelerator error")
                    continue

                # Serialize result (measure tobytes separately from send)
                t_ser_start = time.time()
                M_out, N_out = result.shape
                header = struct.pack(RESP_HDR_FMT, request_id, STATUS_OK,
                                     M_out, N_out, compute_us, deser_us, 0)
                body = result.astype(np.float32).tobytes()
                ser_us = int((time.time() - t_ser_start) * 1_000_000)
                # Re-pack header with actual ser_us
                header = struct.pack(RESP_HDR_FMT, request_id, STATUS_OK,
                                     M_out, N_out, compute_us, deser_us, ser_us)
                self.request.sendall(header + body)

                logger.info(
                    f"[{rid_short}] Done — compute={compute_us}us "
                    f"deser={deser_us}us ser={ser_us}us"
                )

        except Exception:
            logger.exception(f"Error handling connection from {peer}")
        finally:
            logger.info(f"Connection from {peer} closed")


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bitstream', default='design_1_wrapper.bit')
    parser.add_argument('--frac-bits', type=int, default=None,
                        help='Fixed-point fractional bits')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    logger.info(f"Loading bitstream: {args.bitstream}")
    accel = MatrixAccelerator(args.bitstream, frac_bits=args.frac_bits)
    atexit.register(accel.close)
    logger.info(
        f"Accelerator ready ({N_ROWS}x{N_COLS} array, "
        f"TILE_DEPTH={TILE_DEPTH}, frac_bits={accel.frac_bits})"
    )

    server = ThreadedTCPServer(('0.0.0.0', args.port), TileHandler)
    logger.info(f"TCP server listening on 0.0.0.0:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()
