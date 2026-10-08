import numpy as np
import pytest

from backend.services.slicer import pad_matrix, slice_matrix, strip_padding


class TestPadMatrix:
    def test_exact_multiple(self):
        m = np.ones((4, 4))
        result = pad_matrix(m, 4)
        assert result.shape == (4, 4)
        np.testing.assert_array_equal(result, m)

    def test_needs_padding(self):
        m = np.ones((3, 5))
        result = pad_matrix(m, 4)
        assert result.shape == (4, 8)
        # Original values preserved
        np.testing.assert_array_equal(result[:3, :5], np.ones((3, 5)))
        # Padding is zeros
        np.testing.assert_array_equal(result[3:, :], 0)
        np.testing.assert_array_equal(result[:, 5:], 0)

    def test_single_element(self):
        m = np.array([[42.0]])
        result = pad_matrix(m, 4)
        assert result.shape == (4, 4)
        assert result[0, 0] == 42.0

    def test_rectangular(self):
        m = np.ones((6, 2))
        result = pad_matrix(m, 4)
        assert result.shape == (8, 4)


class TestSliceMatrix:
    def test_basic_slice(self):
        m = np.arange(16).reshape(4, 4).astype(float)
        tiles = slice_matrix(m, 2)
        assert len(tiles) == 2
        assert len(tiles[0]) == 2
        np.testing.assert_array_equal(tiles[0][0], [[0, 1], [4, 5]])
        np.testing.assert_array_equal(tiles[1][1], [[10, 11], [14, 15]])

    def test_single_tile(self):
        m = np.ones((4, 4))
        tiles = slice_matrix(m, 4)
        assert len(tiles) == 1
        assert len(tiles[0]) == 1

    def test_rectangular(self):
        m = np.ones((4, 8))
        tiles = slice_matrix(m, 4)
        assert len(tiles) == 1
        assert len(tiles[0]) == 2

    def test_not_multiple_raises(self):
        m = np.ones((3, 3))
        with pytest.raises(ValueError):
            slice_matrix(m, 4)


class TestStripPadding:
    def test_strip(self):
        m = np.ones((8, 8))
        result = strip_padding(m, 5, 6)
        assert result.shape == (5, 6)

    def test_no_strip_needed(self):
        m = np.ones((4, 4))
        result = strip_padding(m, 4, 4)
        assert result.shape == (4, 4)
