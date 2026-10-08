#include <ap_int.h>

// ============================================================================
// CONFIGURATION PARAMETERS
// ============================================================================
#define N_ROWS 16
#define N_COLS 16
#define TILE_DEPTH 128
#define ELEMS_PER_WORD 16          // 256 bits / 16 bits per element
#define WORDS_PER_ROW  (TILE_DEPTH / ELEMS_PER_WORD)  // 8

typedef short data_t;
typedef ap_int<48> acc_t;
typedef ap_uint<256> wide_t;       // 256-bit AXI bus = 16 x 16-bit elements

// ============================================================================
// HELPER — extract a 16-bit signed element from a 256-bit word
// ============================================================================
static data_t extract(wide_t word, int idx) {
    #pragma HLS INLINE
    return (short)(ap_int<16>)word(idx * 16 + 15, idx * 16);
}

// ============================================================================
// WIDE-FORMAT LOAD — store raw 256-bit words (no unpack)
// ============================================================================

// Load A tile: 16 rows x 8 words/row = 128 wide reads, ~143 cycles at II=1.
void load_A_wide(wide_t buf[N_ROWS][WORDS_PER_ROW], wide_t *mem_A,
                 int ti, int tk, int K_words) {
    LOAD_A: for (int i = 0; i < N_ROWS; i++) {
        for (int kw = 0; kw < WORDS_PER_ROW; kw++) {
            #pragma HLS PIPELINE II=1
            buf[i][kw] = mem_A[(ti * N_ROWS + i) * K_words
                               + tk * WORDS_PER_ROW + kw];
        }
    }
}

// Load B tile: 128 wide reads (one word per k-row), ~142 cycles at II=1.
void load_B_wide(wide_t buf[TILE_DEPTH], wide_t *mem_B,
                 int tj, int tk, int N_words) {
    LOAD_B: for (int k = 0; k < TILE_DEPTH; k++) {
        #pragma HLS PIPELINE II=1
        buf[k] = mem_B[(tk * TILE_DEPTH + k) * N_words + tj];
    }
}

// ============================================================================
// MERGED COMPUTE + PREFETCH — single 256-iteration pipelined loop
//
// Computes from a_cur/b_cur (wide_t format, extract elements on the fly)
// while prefetching the next tile into a_nxt/b_nxt as raw wide_t words.
//
// Single loop with interleaved row groups → one pipeline instance, one set
// of 128 MACs.  Prefetch in first 128 iterations only (conditional on
// loop counter — compile-time predictable).
//
// Buffers use wide_t (256-bit) with dim=1 complete and LUTRAM binding.
// This gives only 16 banks per array (vs 256 with cyclic=16 on data_t),
// keeping MUX overhead manageable.  Element extraction via bit-slicing
// adds ~2K LUT but avoids the 25K+ MUX penalty of fine-grained partitioning.
// ============================================================================
void compute_and_prefetch(
    wide_t a_cur[N_ROWS][WORDS_PER_ROW],
    wide_t b_cur[TILE_DEPTH],
    wide_t a_nxt[N_ROWS][WORDS_PER_ROW],
    wide_t b_nxt[TILE_DEPTH],
    acc_t  local_C[N_ROWS][N_COLS],
    wide_t *mem_A, wide_t *mem_B,
    int ti, int tk_nxt, int tj,
    int K_words, int N_words
) {
    #pragma HLS INLINE off
    #pragma HLS ARRAY_PARTITION variable=a_cur dim=1 complete

    static const int GROUP_SIZE = N_ROWS / 2;

    MERGED: for (int iter = 0; iter < TILE_DEPTH * 2; iter++) {
        #pragma HLS PIPELINE II=1

        int t        = iter >> 1;
        int ig       = iter & 1;
        int row_base = ig * GROUP_SIZE;
        int word_idx = t >> 4;           // t / 16
        int elem_idx = t & 0xF;          // t % 16

        // Read B word (one 256-bit LUTRAM read)
        wide_t b_word = b_cur[t];

        // --- COMPUTE: 128 MACs ---
        for (int ii = 0; ii < GROUP_SIZE; ii++) {
            #pragma HLS UNROLL
            wide_t a_word = a_cur[row_base + ii][word_idx];
            data_t a_val  = extract(a_word, elem_idx);
            for (int j = 0; j < N_COLS; j++) {
                #pragma HLS UNROLL
                data_t b_val = extract(b_word, j);
                local_C[row_base + ii][j] += (acc_t)a_val * (acc_t)b_val;
            }
        }

        // --- PREFETCH (first TILE_DEPTH iterations only) ---
        if (iter < TILE_DEPTH) {
            // A: one raw 256-bit word into LUTRAM
            int i_a  = iter >> 3;       // row 0..15
            int kw_a = iter & 7;        // word 0..7
            a_nxt[i_a][kw_a] = mem_A[(ti * N_ROWS + i_a) * K_words
                                      + tk_nxt * WORDS_PER_ROW + kw_a];
            // B: one raw 256-bit word into LUTRAM
            b_nxt[iter] = mem_B[(tk_nxt * TILE_DEPTH + iter) * N_words + tj];
        }
    }
}

// ============================================================================
// TOP-LEVEL ORCHESTRATOR — DOUBLE-BUFFERED COMPUTE + PREFETCH
//
// Two buffer sets of wide_t arrays enable ping-pong.  BIND_STORAGE forces
// LUTRAM (distributed RAM), avoiding the 8-BRAM18K-per-bank penalty of
// storing 256-bit words in block RAM.
//
// Per-k-tile timing (after prolog):
//   Merged loop: ~270 cycles (load fully hidden in first 128 iterations)
// Prolog (first tile): 143 + 128 = 271 cycles (sequential load, no overlap)
// Last tile: dummy prefetch (re-reads same address; data discarded)
// ============================================================================
void systolic_tile_processor(
    wide_t *mem_A,
    wide_t *mem_B,
    acc_t  *mem_C,
    int M,
    int N,
    int K
) {
    #pragma HLS INTERFACE m_axi port=mem_A offset=slave bundle=gmem0 depth=16384
    #pragma HLS INTERFACE m_axi port=mem_B offset=slave bundle=gmem1 depth=16384
    #pragma HLS INTERFACE m_axi port=mem_C offset=slave bundle=gmem2 depth=262144

    #pragma HLS INTERFACE s_axilite port=M      bundle=control
    #pragma HLS INTERFACE s_axilite port=N      bundle=control
    #pragma HLS INTERFACE s_axilite port=K      bundle=control
    #pragma HLS INTERFACE s_axilite port=return  bundle=control

    // Double buffers — wide_t format, forced to LUTRAM
    wide_t a_wide_0[N_ROWS][WORDS_PER_ROW];
    wide_t a_wide_1[N_ROWS][WORDS_PER_ROW];
    wide_t b_wide_0[TILE_DEPTH];
    wide_t b_wide_1[TILE_DEPTH];
    acc_t  local_C[N_ROWS][N_COLS];

    #pragma HLS ARRAY_PARTITION variable=a_wide_0 dim=1 complete
    #pragma HLS ARRAY_PARTITION variable=a_wide_1 dim=1 complete
    #pragma HLS BIND_STORAGE variable=a_wide_0 type=RAM_S2P impl=LUTRAM
    #pragma HLS BIND_STORAGE variable=a_wide_1 type=RAM_S2P impl=LUTRAM
    #pragma HLS BIND_STORAGE variable=b_wide_0 type=RAM_S2P impl=LUTRAM
    #pragma HLS BIND_STORAGE variable=b_wide_1 type=RAM_S2P impl=LUTRAM
    #pragma HLS ARRAY_PARTITION variable=local_C complete dim=0

    int tiles_m = M / N_ROWS;
    int tiles_n = N / N_COLS;
    int tiles_k = K / TILE_DEPTH;
    int K_words = K >> 4;          // K / 16
    int N_words = N >> 4;          // N / 16

    TILE_I: for (int ti = 0; ti < tiles_m; ti++) {
        #pragma HLS LOOP_TRIPCOUNT min=1 max=16
        TILE_J: for (int tj = 0; tj < tiles_n; tj++) {
            #pragma HLS LOOP_TRIPCOUNT min=1 max=16

            // Zero local accumulator
            for (int i = 0; i < N_ROWS; i++) {
                #pragma HLS UNROLL
                for (int j = 0; j < N_COLS; j++) {
                    #pragma HLS UNROLL
                    local_C[i][j] = 0;
                }
            }

            // Prolog: load first k-tile into buffer set 0
            load_A_wide(a_wide_0, mem_A, ti, 0, K_words);
            load_B_wide(b_wide_0, mem_B, tj, 0, N_words);

            // Process k-tiles with double-buffered prefetch.
            // Last tile uses dummy prefetch (re-reads same addresses).
            TILE_K: for (int tk = 0; tk < tiles_k; tk++) {
                #pragma HLS LOOP_TRIPCOUNT min=1 max=8

                int tk_nxt = (tk < tiles_k - 1) ? tk + 1 : tk;

                if ((tk & 1) == 0)
                    compute_and_prefetch(
                        a_wide_0, b_wide_0, a_wide_1, b_wide_1,
                        local_C, mem_A, mem_B,
                        ti, tk_nxt, tj, K_words, N_words);
                else
                    compute_and_prefetch(
                        a_wide_1, b_wide_1, a_wide_0, b_wide_0,
                        local_C, mem_A, mem_B,
                        ti, tk_nxt, tj, K_words, N_words);
            } // end TILE_K

            // --- STORE completed C tile ---
            STORE_C: for (int idx = 0; idx < N_ROWS * N_COLS; idx++) {
                #pragma HLS PIPELINE II=1
                int i = idx / N_COLS;
                int j = idx % N_COLS;
                mem_C[(ti * N_ROWS + i) * N + tj * N_COLS + j] = local_C[i][j];
            }
        } // end TILE_J
    } // end TILE_I
}
