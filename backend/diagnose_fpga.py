"""
Diagnostic script to test the FPGA board's TCP binary protocol directly.
Run from the project root:
    python -m backend.diagnose_fpga [--host 192.168.2.99] [--port 5000]
"""

import argparse
import socket
import struct
import sys
import time

import numpy as np

from backend.services.protocol import (
    REQ_HDR_FMT, REQ_HDR_SIZE,
    RESP_HDR_FMT, RESP_HDR_SIZE,
    ERR_HDR_FMT,
    STATUS_OK, FLAG_RETURN_FULL,
    pack_request, recv_exact,
)


def send_multiply(sock, mat_a: np.ndarray, mat_b: np.ndarray,
                  frac_bits: int) -> dict:
    """Send a multiply request and return parsed response."""
    import uuid
    request_id = uuid.uuid4().bytes

    a_i16 = np.clip(np.round(mat_a * (1 << frac_bits)), -32768, 32767).astype(np.int16)
    b_i16 = np.clip(np.round(mat_b * (1 << frac_bits)), -32768, 32767).astype(np.int16)
    M, K = a_i16.shape
    _, N = b_i16.shape

    header = pack_request(request_id, M, K, N, frac_bits, FLAG_RETURN_FULL)
    sock.sendall(header + a_i16.tobytes() + b_i16.tobytes())

    # Read response
    resp_prefix = recv_exact(sock, 17)
    resp_id = resp_prefix[:16]
    status = resp_prefix[16]

    if status != STATUS_OK:
        err_len = struct.unpack("!H", recv_exact(sock, 2))[0]
        err_msg = recv_exact(sock, err_len).decode("utf-8")
        return {"status": "error", "error": err_msg}

    rest = recv_exact(sock, RESP_HDR_SIZE - 17)
    resp_M, resp_N, compute_us, deser_us, ser_us = struct.unpack("!IIIII", rest)

    body = recv_exact(sock, resp_M * resp_N * 4)
    result = np.frombuffer(body, dtype=np.float32).reshape(resp_M, resp_N)

    return {
        "status": "ok",
        "result": result,
        "shape": (resp_M, resp_N),
        "compute_us": compute_us,
        "deser_us": deser_us,
        "ser_us": ser_us,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.2.99")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    print(f"Testing FPGA at {args.host}:{args.port} (TCP binary protocol)\n")

    # Connect
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30)
        sock.connect((args.host, args.port))
    except Exception as e:
        print(f"   CONNECTION FAILED: {e}")
        sys.exit(1)

    # 1. Health check (M=0)
    print("=" * 60)
    print("1. Health check (M=0 header)")
    print("=" * 60)
    try:
        import uuid
        rid = uuid.uuid4().bytes
        header = pack_request(rid, 0, 0, 0, 9, 0)
        sock.sendall(header)

        resp = recv_exact(sock, RESP_HDR_SIZE)
        _, status, tile_rows, tile_cols, tile_depth, frac_bits_hw, max_dim = struct.unpack(
            RESP_HDR_FMT, resp
        )
        print(f"   Status: {'ok' if status == STATUS_OK else 'error'}")
        print(f"   Hardware: rows={tile_rows}, cols={tile_cols}, depth={tile_depth}")
        print(f"   frac_bits={frac_bits_hw}, MAX_DIM={max_dim}")
        frac_bits = frac_bits_hw if frac_bits_hw > 0 else 9
    except Exception as e:
        print(f"   FAILED: {e}")
        sock.close()
        sys.exit(1)

    # Use dimensions compatible with hardware
    from math import lcm
    test_dim = lcm(tile_rows, tile_cols, tile_depth)

    # 2. Identity test
    print()
    print("=" * 60)
    print(f"2. Identity test ({test_dim}x{test_dim}): I @ I should = I")
    print("=" * 60)
    I_mat = np.eye(test_dim, dtype=np.float32)
    data = send_multiply(sock, I_mat, I_mat, frac_bits)
    if data["status"] == "error":
        print(f"   ERROR: {data['error']}")
    else:
        C = data["result"]
        print(f"   Result shape: {C.shape}")
        print(f"   Diagonal sample: {C[0,0]:.6f}, {C[1,1]:.6f}, {C[2,2]:.6f}")
        print(f"   Off-diagonal sample: {C[0,1]:.6f}, {C[1,0]:.6f}")
        err = np.max(np.abs(C - I_mat))
        print(f"   Max error vs identity: {err:.6e}")
        print(f"   {'PASS' if err < 0.1 else '*** FAIL'}")
        print(f"   Timings: compute={data['compute_us']}us deser={data['deser_us']}us")

    # 3. Ones multiplication
    print()
    print("=" * 60)
    print(f"3. Known multiplication: ones({test_dim},{test_dim}) @ ones({test_dim},{test_dim})")
    print(f"   Expected: every element = {test_dim}.0")
    print("=" * 60)
    A = np.ones((test_dim, test_dim), dtype=np.float32)
    B = np.ones((test_dim, test_dim), dtype=np.float32)
    data = send_multiply(sock, A, B, frac_bits)
    if data["status"] == "error":
        print(f"   ERROR: {data['error']}")
    else:
        C = data["result"]
        expected = float(test_dim)
        print(f"   Result[0,0] = {C[0,0]:.6f}  (expected {expected})")
        err = np.max(np.abs(C - expected))
        print(f"   Max error: {err:.6e}")
        if abs(C[0, 0] - expected) > 1:
            ratio = C[0, 0] / expected
            print(f"   *** SCALING ISSUE: result/expected = {ratio:.2f}")
        else:
            print(f"   {'PASS' if err < 1.0 else '*** FAIL'}")

    # 4. Random tile-sized test (256x256)
    print()
    print("=" * 60)
    print("4. Random tile test (256x256) — same size orchestrator sends")
    print("=" * 60)
    rng = np.random.default_rng(42)
    safe_range = 2 ** (16 - 1 - frac_bits) * 0.9
    A = np.clip(rng.standard_normal((256, 256)), -safe_range, safe_range).astype(np.float32)
    B = np.clip(rng.standard_normal((256, 256)), -safe_range, safe_range).astype(np.float32)
    golden = A.astype(np.float64) @ B.astype(np.float64)

    t0 = time.time()
    data = send_multiply(sock, A, B, frac_bits)
    wall_time = time.time() - t0

    if data["status"] == "error":
        print(f"   ERROR: {data['error']}")
    else:
        C = data["result"].astype(np.float64)
        print(f"   Result shape: {C.shape}")
        diff = np.abs(C - golden)
        max_err = np.max(diff)
        mean_err = np.mean(diff)
        print(f"   Max abs error:  {max_err:.6e}")
        print(f"   Mean abs error: {mean_err:.6e}")
        print(f"   Golden[0,0]={golden[0,0]:.4f}  FPGA[0,0]={C[0,0]:.4f}")
        print(f"   Wall time: {wall_time:.3f}s")
        print(f"   Board compute: {data['compute_us']/1e6:.3f}s")
        if max_err < 1.0:
            print(f"   PASS")
        elif max_err < 10.0:
            print(f"   MARGINAL — precision limited by frac_bits={frac_bits}")
        else:
            print(f"   *** FAIL — error too large")

    # 5. Random unclamped test
    print()
    print("=" * 60)
    print("5. Random test (256x256, unclamped standard_normal)")
    print("=" * 60)
    A_raw = rng.standard_normal((256, 256)).astype(np.float32)
    B_raw = rng.standard_normal((256, 256)).astype(np.float32)
    golden_raw = A_raw.astype(np.float64) @ B_raw.astype(np.float64)

    data = send_multiply(sock, A_raw, B_raw, frac_bits)
    if data["status"] == "error":
        print(f"   ERROR: {data['error']}")
    else:
        C = data["result"].astype(np.float64)
        diff = np.abs(C - golden_raw)
        max_err = np.max(diff)
        mean_err = np.mean(diff)
        print(f"   Max abs error:  {max_err:.6e}")
        print(f"   Mean abs error: {mean_err:.6e}")
        if frac_bits >= 13:
            clipped = np.sum(np.abs(A_raw) > safe_range) + np.sum(np.abs(B_raw) > safe_range)
            total = A_raw.size + B_raw.size
            print(f"   Values clipped: {clipped}/{total} ({100*clipped/total:.1f}%)")

    # 6. Throughput test (multiple tiles on same connection)
    print()
    print("=" * 60)
    print("6. Throughput: 4 sequential 256x256 tiles on same connection")
    print("=" * 60)
    t0 = time.time()
    for tile_i in range(4):
        A_t = np.clip(rng.standard_normal((256, 256)), -safe_range, safe_range).astype(np.float32)
        B_t = np.clip(rng.standard_normal((256, 256)), -safe_range, safe_range).astype(np.float32)
        data = send_multiply(sock, A_t, B_t, frac_bits)
        if data["status"] == "error":
            print(f"   Tile {tile_i}: ERROR: {data['error']}")
            break
        print(f"   Tile {tile_i}: compute={data['compute_us']}us")
    total = time.time() - t0
    print(f"   Total wall time: {total:.3f}s ({total/4:.3f}s per tile)")

    sock.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
