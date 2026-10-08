import asyncio
import struct

import numpy as np
import pytest

from backend.models.schemas import TileStatus, TileStatusEvent, JobCompleteEvent
from backend.models.state import Job
from backend.services.orchestrator import run_job
from backend.services.protocol import (
    REQ_HDR_FMT, REQ_HDR_SIZE,
    RESP_HDR_FMT, RESP_HDR_SIZE,
    STATUS_OK, pack_response,
)


class MockTCPServer:
    """Mock TCP server that performs numpy matmul and responds with binary protocol."""

    def __init__(self, delay: float = 0.0, fail_after: int | None = None):
        self.delay = delay
        self.fail_after = fail_after
        self.call_count = 0
        self._server = None
        self.host = "127.0.0.1"
        self.port = 0  # assigned on start

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_connection, self.host, 0
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter):
        try:
            while True:
                try:
                    raw_header = await reader.readexactly(REQ_HDR_SIZE)
                except asyncio.IncompleteReadError:
                    break

                request_id, M, K, N, frac_bits, flags = struct.unpack(
                    REQ_HDR_FMT, raw_header
                )

                # Health check
                if M == 0:
                    header = struct.pack(RESP_HDR_FMT, request_id, STATUS_OK,
                                         8, 8, 128, 9, 1024)
                    writer.write(header)
                    await writer.drain()
                    continue

                # Read matrix data
                a_bytes = await reader.readexactly(M * K * 2)
                b_bytes = await reader.readexactly(K * N * 2)

                self.call_count += 1

                if self.fail_after and self.call_count > self.fail_after:
                    writer.close()
                    return

                mat_a = np.frombuffer(a_bytes, dtype=np.int16).reshape(M, K)
                mat_b = np.frombuffer(b_bytes, dtype=np.int16).reshape(K, N)

                if self.delay > 0:
                    await asyncio.sleep(self.delay)

                # Simulate fixed-point MAC
                raw = mat_a.astype(np.int64) @ mat_b.astype(np.int64)
                result = raw.astype(np.float32) / (1 << (2 * frac_bits))

                resp_M, resp_N = result.shape
                header = pack_response(request_id, resp_M, resp_N, 0, 0, 0)
                body = result.astype(np.float32).tobytes()
                writer.write(header + body)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.mark.asyncio
async def test_full_pipeline_small(monkeypatch):
    """8x8 matrix, tile_size=4 -- should match np.matmul within fixed-point tolerance."""
    rng = np.random.default_rng(42)
    A = rng.standard_normal((8, 8))
    B = rng.standard_normal((8, 8))

    job = Job(A, B, tile_size=4)

    mock_server = MockTCPServer()
    await mock_server.start()

    monkeypatch.setattr("backend.services.orchestrator.settings.FPGA_HOST", mock_server.host)
    monkeypatch.setattr("backend.services.orchestrator.settings.FPGA_PORT", mock_server.port)

    try:
        await run_job(job)
    finally:
        await mock_server.stop()

    assert job.finished
    assert job.result is not None

    expected = np.matmul(A, B)
    # Fixed-point int16 introduces quantization error; use atol=0.5
    np.testing.assert_allclose(job.result, expected, atol=0.5)

    # 2x2x2 = 8 tile operations
    assert job.completed_count == 8
    assert job.phase_timings is not None


@pytest.mark.asyncio
async def test_non_square_matrix(monkeypatch):
    """Test rectangular matrices: (6x10) * (10x4), tile_size=4."""
    rng = np.random.default_rng(123)
    A = rng.standard_normal((6, 10))
    B = rng.standard_normal((10, 4))

    job = Job(A, B, tile_size=4)

    mock_server = MockTCPServer()
    await mock_server.start()

    monkeypatch.setattr("backend.services.orchestrator.settings.FPGA_HOST", mock_server.host)
    monkeypatch.setattr("backend.services.orchestrator.settings.FPGA_PORT", mock_server.port)

    try:
        await run_job(job)
    finally:
        await mock_server.stop()

    assert job.finished
    expected = np.matmul(A, B)
    np.testing.assert_allclose(job.result, expected, atol=0.5)
    assert job.result.shape == (6, 4)


@pytest.mark.asyncio
async def test_cancellation(monkeypatch):
    """Cancel job mid-execution."""
    A = np.ones((8, 8))
    B = np.ones((8, 8))
    job = Job(A, B, tile_size=4)

    call_count = 0

    mock_timings = {
        "client_serialization_sec": 0.0,
        "network_round_trip_sec": 0.0,
        "client_deserialization_sec": 0.0,
        "board_deserialization_sec": 0.0,
        "board_computation_sec": 0.0,
        "board_serialization_sec": 0.0,
    }

    async def mock_dispatch(reader, writer, a_tile, b_tile,
                            frac_bits=9, timeout=60):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            job.cancelled = True
        return np.matmul(a_tile, b_tile), mock_timings.copy()

    monkeypatch.setattr("backend.services.orchestrator.dispatch_tile", mock_dispatch)

    # Still need valid host/port for connection pool (mock_dispatch bypasses it,
    # but we monkeypatch dispatch_tile directly — need to also skip connection setup)
    # Simplest: monkeypatch open_connection to return dummy reader/writer
    async def mock_open_connection(host, port):
        reader = asyncio.StreamReader()
        return reader, MockWriter()

    monkeypatch.setattr("backend.services.orchestrator.asyncio.open_connection",
                        mock_open_connection)

    await run_job(job)

    assert job.finished
    assert job.cancelled
    assert job.completed_count < 8


class MockWriter:
    """Minimal asyncio.StreamWriter mock for cancellation test."""

    def close(self):
        pass

    async def wait_closed(self):
        pass
