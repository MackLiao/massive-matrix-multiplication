import numpy as np

from backend.services.accumulator import accumulate


class TestAccumulate:
    def test_basic_accumulate(self):
        C = np.zeros((4, 4))
        tile = np.ones((2, 2))
        accumulate(C, tile, 0, 0, 2)
        np.testing.assert_array_equal(C[:2, :2], np.ones((2, 2)))
        np.testing.assert_array_equal(C[2:, :], 0)

    def test_accumulate_adds(self):
        C = np.ones((4, 4))
        tile = np.full((2, 2), 3.0)
        accumulate(C, tile, 1, 1, 2)
        # Position (1,1) should be 1 + 3 = 4
        np.testing.assert_array_equal(C[2:4, 2:4], np.full((2, 2), 4.0))
        # Other positions unchanged
        np.testing.assert_array_equal(C[:2, :2], np.ones((2, 2)))

    def test_multiple_accumulations(self):
        """Simulate k-loop: accumulate multiple tiles into same (i,j) block."""
        C = np.zeros((2, 2))
        for _ in range(3):
            tile = np.ones((2, 2))
            accumulate(C, tile, 0, 0, 2)
        np.testing.assert_array_equal(C, np.full((2, 2), 3.0))
