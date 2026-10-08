import asyncio
import logging
import time

import numpy as np

from ..config import settings
from ..models.schemas import JobCompleteEvent, TileStatus, TileStatusEvent
from ..models.state import Job
from .accumulator import accumulate
from .dispatcher import dispatch_tile
from .slicer import pad_matrix, slice_matrix, strip_padding

logger = logging.getLogger(__name__)

PHASE_KEYS = [
    "client_serialization_sec",
    "network_round_trip_sec",
    "client_deserialization_sec",
    "board_deserialization_sec",
    "board_computation_sec",
    "board_serialization_sec",
    "accumulation_sec",
]


def _aggregate_timings(tile_timings: list[dict]) -> dict:
    """Aggregate per-tile timings into summary stats per phase."""
    if not tile_timings:
        return {}

    result = {}
    for key in PHASE_KEYS:
        values = [t[key] for t in tile_timings if t.get(key) is not None]
        if not values:
            continue
        result[key] = {
            "total": round(sum(values), 6),
            "mean": round(sum(values) / len(values), 6),
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "count": len(values),
        }
    return result


async def run_job(job: Job) -> None:
    """Run the blocked matrix multiplication job with pipelined dispatch.

    Opens PIPELINE_DEPTH persistent TCP connections to the FPGA board.
    Uses a connection pool so tiles grab a connection, send/receive, and
    return it — overlapping network transfer with FPGA compute.
    """

    T = job.tile_size
    M, K = job.matrix_a.shape
    _, N = job.matrix_b.shape

    # Pad matrices
    A_padded = pad_matrix(job.matrix_a, T)
    B_padded = pad_matrix(job.matrix_b, T)

    # Slice into tile grids
    A_tiles = slice_matrix(A_padded, T)
    B_tiles = slice_matrix(B_padded, T)

    # Init result matrix (padded size)
    C = np.zeros((A_padded.shape[0], B_padded.shape[1]), dtype=np.float64)

    all_tile_timings: list[dict] = []

    # Open TCP connection pool
    conn_pool: asyncio.Queue[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = asyncio.Queue()
    connections: list[tuple[asyncio.StreamReader, asyncio.StreamWriter]] = []

    try:
        for _ in range(settings.PIPELINE_DEPTH):
            reader, writer = await asyncio.open_connection(
                settings.FPGA_HOST, settings.FPGA_PORT
            )
            connections.append((reader, writer))
            conn_pool.put_nowait((reader, writer))

        async def process_tile(i, j, k):
            if job.cancelled:
                return

            # Acquire a connection from the pool
            reader, writer = await conn_pool.get()

            # Mark in-flight
            job.set_tile_status(i, j, k, TileStatus.IN_FLIGHT)
            await job.event_queue.put(
                TileStatusEvent(
                    i=i, j=j, k=k,
                    status=TileStatus.IN_FLIGHT,
                    completed=job.completed_count,
                    total=job.total_ops,
                    elapsed=time.time() - job.start_time,
                )
            )

            status = TileStatus.FAILED
            for attempt in range(settings.MAX_RETRIES):
                try:
                    result_tile, tile_timings = await dispatch_tile(
                        reader,
                        writer,
                        A_tiles[i][k],
                        B_tiles[k][j],
                        frac_bits=settings.FRAC_BITS,
                        timeout=settings.REQUEST_TIMEOUT,
                    )
                    t_accum_start = time.time()
                    accumulate(C, result_tile, i, j, T)
                    tile_timings["accumulation_sec"] = round(time.time() - t_accum_start, 6)
                    tile_timings["tile"] = (i, j, k)
                    all_tile_timings.append(tile_timings)

                    job.set_tile_status(i, j, k, TileStatus.COMPLETED)
                    status = TileStatus.COMPLETED
                    break
                except Exception as e:
                    # Connection may be in a broken state — replace it
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass
                    if attempt < settings.MAX_RETRIES - 1:
                        wait = settings.RETRY_BACKOFF_BASE ** (attempt + 1)
                        logger.warning(
                            f"Tile ({i},{j},{k}) attempt {attempt + 1} failed: {e}. "
                            f"Reconnecting in {wait}s..."
                        )
                        await asyncio.sleep(wait)
                        try:
                            reader, writer = await asyncio.open_connection(
                                settings.FPGA_HOST, settings.FPGA_PORT
                            )
                        except Exception:
                            reader, writer = None, None
                            break
                    else:
                        logger.error(
                            f"Tile ({i},{j},{k}) failed after {settings.MAX_RETRIES} "
                            f"attempts: {e}"
                        )
                        job.set_tile_status(i, j, k, TileStatus.FAILED)
                        if settings.STOP_ON_FAILURE:
                            job.cancelled = True

            # Return (possibly refreshed) connection to pool
            if reader is not None and writer is not None:
                conn_pool.put_nowait((reader, writer))

            await job.event_queue.put(
                TileStatusEvent(
                    i=i, j=j, k=k,
                    status=status,
                    completed=job.completed_count,
                    total=job.total_ops,
                    elapsed=time.time() - job.start_time,
                )
            )

            if status == TileStatus.FAILED and settings.STOP_ON_FAILURE:
                raise RuntimeError(f"Tile ({i},{j},{k}) failed, stopping job")

        # Build ordered task list
        tile_tasks = [
            (i, j, k)
            for i in range(job.I)
            for j in range(job.J)
            for k in range(job.K_tiles)
        ]

        pending: list[asyncio.Task] = []
        stop = False
        for i, j, k in tile_tasks:
            if job.cancelled or stop:
                break

            task = asyncio.create_task(process_tile(i, j, k))
            pending.append(task)

            # When we hit the pipeline depth, wait for one to complete
            if len(pending) >= settings.PIPELINE_DEPTH:
                done, pending_set = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )
                for t in done:
                    try:
                        await t
                    except RuntimeError:
                        stop = True
                pending = list(pending_set)

        # Drain remaining tasks
        if pending:
            results = await asyncio.gather(*pending, return_exceptions=True)
            for r in results:
                if isinstance(r, RuntimeError):
                    stop = True

    finally:
        # Close all TCP connections
        for _, writer in connections:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    if job.cancelled or stop:
        logger.info(f"Job {job.job_id} cancelled/stopped")
        job.finished = True
        await job.event_queue.put(None)
        return

    # Strip padding and store result
    job.result = strip_padding(C, M, N)
    job.finished = True
    elapsed = time.time() - job.start_time

    # Aggregate per-phase timing stats
    phase_timings = _aggregate_timings(all_tile_timings)
    job.phase_timings = phase_timings

    await job.event_queue.put(
        JobCompleteEvent(
            status="completed",
            completed=job.completed_count,
            total=job.total_ops,
            elapsed=elapsed,
            phase_timings=phase_timings,
        )
    )
    await job.event_queue.put(None)
    logger.info(f"Job {job.job_id} completed in {elapsed:.1f}s")
    logger.info(f"Phase timings: {phase_timings}")
