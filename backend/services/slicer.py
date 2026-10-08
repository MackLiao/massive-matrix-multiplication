import numpy as np


def pad_matrix(m: np.ndarray, tile_size: int) -> np.ndarray:
    """Zero-pad matrix so both dimensions are multiples of tile_size."""
    rows, cols = m.shape
    pad_rows = (tile_size - rows % tile_size) % tile_size
    pad_cols = (tile_size - cols % tile_size) % tile_size
    if pad_rows == 0 and pad_cols == 0:
        return m
    return np.pad(m, ((0, pad_rows), (0, pad_cols)), mode="constant", constant_values=0)


def slice_matrix(m: np.ndarray, tile_size: int) -> list[list[np.ndarray]]:
    """Slice a padded matrix into a 2D grid of tiles."""
    rows, cols = m.shape
    if rows % tile_size != 0:
        raise ValueError(f"rows {rows} not multiple of {tile_size}")
    if cols % tile_size != 0:
        raise ValueError(f"cols {cols} not multiple of {tile_size}")
    grid = []
    for i in range(0, rows, tile_size):
        row_tiles = []
        for j in range(0, cols, tile_size):
            row_tiles.append(m[i : i + tile_size, j : j + tile_size].copy())
        grid.append(row_tiles)
    return grid


def strip_padding(C: np.ndarray, orig_rows: int, orig_cols: int) -> np.ndarray:
    """Remove padding to restore original dimensions."""
    return C[:orig_rows, :orig_cols]
