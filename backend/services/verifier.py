import numpy as np

from ..models.schemas import VerificationResult


def verify(
    A: np.ndarray,
    B: np.ndarray,
    C_fpga: np.ndarray,
    tolerance: float = 1e-1,
) -> VerificationResult:
    """Compare FPGA result against numpy golden standard.

    Default tolerance 0.1 accounts for 16-bit fixed-point quantization
    error that accumulates over large inner-dimension dot products.
    """
    C_expected = np.matmul(A.astype(np.float64), B.astype(np.float64))
    diff = np.abs(C_fpga - C_expected)
    max_abs_error = float(np.max(diff))
    mean_abs_error = float(np.mean(diff))
    passed = max_abs_error <= tolerance

    return VerificationResult(
        max_abs_error=max_abs_error,
        mean_abs_error=mean_abs_error,
        passed=passed,
        tolerance=tolerance,
    )
