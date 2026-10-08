from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    FPGA_HOST: str = "192.168.2.99"
    FPGA_PORT: int = 5000
    TILE_SIZE: int = 256
    REQUEST_TIMEOUT: int = 60
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_BASE: float = 2.0
    MAX_MATRIX_DIM: int = 16384
    STOP_ON_FAILURE: bool = False
    PIPELINE_DEPTH: int = 2
    # Fixed-point fractional bits used for client-side int16 encoding.
    # The board's default is 14 (Q1.14, range [-2, ~2)), but we use 9
    # (Q7.8, range [-128, ~128)) to avoid clipping standard-normal values.
    # This value is sent in the payload so the board scales correctly.
    FRAC_BITS: int = 9

    model_config = {"env_prefix": "CAPSTONE_"}


settings = Settings()
