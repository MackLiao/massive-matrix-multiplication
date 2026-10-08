import numpy as np


def accumulate(
    C: np.ndarray,
    tile_result: np.ndarray,
    i: int,
    j: int,
    tile_size: int,
) -> None:
    """In-place accumulate tile_result into C at block position (i, j)."""
    r_start = i * tile_size
    c_start = j * tile_size
    r_end = r_start + tile_size
    c_end = c_start + tile_size
    C[r_start:r_end, c_start:c_end] += tile_result
