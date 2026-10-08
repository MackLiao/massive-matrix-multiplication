import asyncio
import io
import uuid

import numpy as np
from fastapi import APIRouter, HTTPException, UploadFile

from ..config import settings
from ..models.schemas import (
    JobInfo,
    MatrixGenerateRequest,
    MatrixInfo,
    MultiplyRequest,
    VerificationResult,
    VerifyRequest,
)
from ..models.state import Job, jobs, matrices, register_job_matrices, cleanup_job
from ..services.orchestrator import run_job
from ..services.verifier import verify

router = APIRouter(prefix="/api")


@router.post("/matrix/generate", response_model=MatrixInfo)
async def generate_matrix(req: MatrixGenerateRequest):
    if req.rows > settings.MAX_MATRIX_DIM or req.cols > settings.MAX_MATRIX_DIM:
        raise HTTPException(400, f"Max dimension is {settings.MAX_MATRIX_DIM}")

    rng = np.random.default_rng(req.seed)
    matrix = rng.standard_normal((req.rows, req.cols))
    matrix_id = str(uuid.uuid4())
    matrices[matrix_id] = matrix

    return MatrixInfo(id=matrix_id, rows=req.rows, cols=req.cols)


@router.post("/matrix/upload", response_model=MatrixInfo)
async def upload_matrix(file: UploadFile):
    MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Upload too large (max 100 MB)")

    if file.content_type and file.content_type not in ("text/csv", "text/plain", "application/octet-stream"):
        raise HTTPException(400, f"Unsupported file type: {file.content_type}. Expected CSV.")

    try:
        matrix = np.loadtxt(io.BytesIO(content), delimiter=",")
    except Exception:
        raise HTTPException(400, "Invalid CSV file")

    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)

    rows, cols = matrix.shape
    if rows > settings.MAX_MATRIX_DIM or cols > settings.MAX_MATRIX_DIM:
        raise HTTPException(400, f"Max dimension is {settings.MAX_MATRIX_DIM}")

    matrix_id = str(uuid.uuid4())
    matrices[matrix_id] = matrix

    return MatrixInfo(id=matrix_id, rows=rows, cols=cols)


@router.get("/matrix/{matrix_id}/info", response_model=MatrixInfo)
async def matrix_info(matrix_id: str):
    if matrix_id not in matrices:
        raise HTTPException(404, "Matrix not found")
    m = matrices[matrix_id]
    return MatrixInfo(id=matrix_id, rows=m.shape[0], cols=m.shape[1])


@router.post("/multiply", response_model=JobInfo)
async def multiply(req: MultiplyRequest):
    if req.matrix_a_id not in matrices:
        raise HTTPException(404, "Matrix A not found")
    if req.matrix_b_id not in matrices:
        raise HTTPException(404, "Matrix B not found")

    A = matrices[req.matrix_a_id]
    B = matrices[req.matrix_b_id]

    if A.shape[1] != B.shape[0]:
        raise HTTPException(
            400,
            f"Incompatible shapes: A is {A.shape}, B is {B.shape}. "
            f"A's columns ({A.shape[1]}) must equal B's rows ({B.shape[0]})",
        )

    if req.tile_size not in (128, 256, 512, 1024, 2048):
        raise HTTPException(400, "Tile size must be 128, 256, 512, 1024, or 2048")

    job = Job(A, B, req.tile_size)
    jobs[job.job_id] = job
    register_job_matrices(job.job_id, req.matrix_a_id, req.matrix_b_id)

    # Store matrix IDs on the job for cleanup
    job.matrix_a_id = req.matrix_a_id
    job.matrix_b_id = req.matrix_b_id

    asyncio.create_task(run_job(job))

    return JobInfo(job_id=job.job_id)


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    jobs[job_id].cancelled = True
    return {"status": "cancelling"}


@router.get("/jobs/{job_id}/timings")
async def job_timings(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    if not job.finished:
        raise HTTPException(400, "Job not finished")
    return {"job_id": job_id, "phase_timings": job.phase_timings}


@router.post("/jobs/{job_id}/verify", response_model=VerificationResult)
async def verify_job(job_id: str, req: VerifyRequest | None = None):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if not job.finished or job.result is None:
        raise HTTPException(400, "Job not finished or has no result")

    tolerance = req.tolerance if req and req.tolerance is not None else 0.1

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, verify, job.matrix_a, job.matrix_b, job.result, tolerance
    )

    # Clean up job and unreferenced matrices after verification
    matrix_a_id = getattr(job, "matrix_a_id", None)
    matrix_b_id = getattr(job, "matrix_b_id", None)
    if matrix_a_id and matrix_b_id:
        cleanup_job(job_id, matrix_a_id, matrix_b_id)

    return result
