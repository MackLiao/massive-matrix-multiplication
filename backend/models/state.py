import asyncio
import time
import uuid

import numpy as np

from .schemas import TileStatus


class Job:
    def __init__(
        self,
        matrix_a: np.ndarray,
        matrix_b: np.ndarray,
        tile_size: int,
    ):
        self.job_id = str(uuid.uuid4())
        self.matrix_a = matrix_a
        self.matrix_b = matrix_b
        self.tile_size = tile_size

        M, K = matrix_a.shape
        _, N = matrix_b.shape
        T = tile_size

        # Padded dimensions
        self.I = (M + T - 1) // T
        self.J = (N + T - 1) // T
        self.K_tiles = (K + T - 1) // T
        self.total_ops = self.I * self.J * self.K_tiles

        # 3D status grid [I][J][K]
        self.tile_status: list[list[list[TileStatus]]] = [
            [
                [TileStatus.PENDING for _ in range(self.K_tiles)]
                for _ in range(self.J)
            ]
            for _ in range(self.I)
        ]

        self.result: np.ndarray | None = None
        self.completed_count = 0
        self.cancelled = False
        self.finished = False
        self.start_time = time.time()
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.phase_timings: dict | None = None

    def set_tile_status(self, i: int, j: int, k: int, status: TileStatus):
        self.tile_status[i][j][k] = status
        if status == TileStatus.COMPLETED:
            self.completed_count += 1


# Global job store
jobs: dict[str, Job] = {}

# Global matrix store
matrices: dict[str, np.ndarray] = {}

# Track which matrices are referenced by active jobs
_matrix_refs: dict[str, set[str]] = {}  # matrix_id -> set of job_ids


def register_job_matrices(job_id: str, matrix_a_id: str, matrix_b_id: str) -> None:
    """Track which matrices are used by a job."""
    for mid in (matrix_a_id, matrix_b_id):
        _matrix_refs.setdefault(mid, set()).add(job_id)


def cleanup_job(job_id: str, matrix_a_id: str, matrix_b_id: str) -> None:
    """Remove a finished/cancelled job and release unreferenced matrices."""
    jobs.pop(job_id, None)
    for mid in (matrix_a_id, matrix_b_id):
        refs = _matrix_refs.get(mid)
        if refs:
            refs.discard(job_id)
            if not refs:
                _matrix_refs.pop(mid, None)
                matrices.pop(mid, None)
