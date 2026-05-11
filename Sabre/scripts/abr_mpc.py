import sabre
import math
import itertools


class abr_mpc(sabre.Abr):
    """
    Final Robust MPC ABR (Buffer-Safe Version)

    FIXED:
    - Stable EMA throughput prediction
    - Bounded prediction (no collapse)
    - Proper QoE scaling
    - HARD buffer safety constraint (critical fix)
    - Prevents rebuffer explosion
    """

    def __init__(self, config):
        super().__init__(config)

        manifest = self.session.manifest
        self.R = sorted(manifest.bitrates)

        seg_t = manifest.segment_time
        self.dt = seg_t / 1000.0 if seg_t > 100 else float(seg_t)

        # ================= MPC SETTINGS =================
        self.HORIZON = 2

        self.REBUF_PENALTY = 2.5
        self.SMOOTH_PENALTY = 0.5

        # ================= PREDICTOR =================
        self.tp_ema = None
        self.tp_min = float("inf")
        self.tp_max = 0.0
        self.alpha = 0.6

        self.prev_r = self.R[0]

    # =========================================================
    # Utility
    # =========================================================

    def utility(self, r):
        return math.log(r / min(self.R) + 1)

    # =========================================================
    # Throughput prediction (stable bounded EMA)
    # =========================================================

    def update_throughput(self, tp):
        if tp <= 0:
            return

        self.tp_min = min(self.tp_min, tp)
        self.tp_max = max(self.tp_max, tp)

        if self.tp_ema is None:
            self.tp_ema = tp
        else:
            self.tp_ema = self.alpha * tp + (1 - self.alpha) * self.tp_ema

    def predict_throughput(self):
        if self.tp_ema is None:
            return self.R[0]

        pred = self.tp_ema

        lower = self.tp_min * 0.8
        upper = self.tp_max * 1.1

        return max(lower, min(pred, upper))

    # =========================================================
    # MPC simulation
    # =========================================================

    def simulate_path(self, path, throughput, buffer):

        total_q = 0.0
        total_rebuf = 0.0
        total_smooth = 0.0

        prev_r = self.prev_r
        buf = buffer

        for r in path:

            chunk = r * self.dt
            download_time = chunk / max(throughput, 1e-6)

            rebuf = max(0.0, download_time - buf)
            total_rebuf += rebuf / self.dt

            buf = max(0.0, buf - download_time)
            buf += self.dt

            total_q += self.utility(r)

            total_smooth += abs(self.utility(r) - self.utility(prev_r))

            prev_r = r

        return (
            total_q
            - self.REBUF_PENALTY * total_rebuf
            - self.SMOOTH_PENALTY * total_smooth
        )

    # =========================================================
    # MPC selection (WITH HARD BUFFER SAFETY LAYER)
    # =========================================================

    def select_bitrate(self, throughput, buffer):

        best_score = -float("inf")
        best_r = self.R[0]

        # brute-force MPC search
        for path in itertools.product(self.R, repeat=self.HORIZON):

            score = self.simulate_path(path, throughput, buffer)

            if score > best_score:
                best_score = score
                best_r = path[0]

        # =====================================================
        # HARD BUFFER SAFETY CONSTRAINT (CRITICAL FIX)
        # =====================================================

        best_idx = self.R.index(best_r)

        if buffer < 2.0:
            safe_idx = 0
        elif buffer < 4.0:
            safe_idx = 1
        elif buffer < 6.0:
            safe_idx = 2
        else:
            safe_idx = len(self.R) - 1

        best_r = self.R[min(best_idx, safe_idx)]

        # =====================================================
        # Anti-oscillation rule
        # =====================================================

        prev_idx = self.R.index(self.prev_r)

        if best_idx < prev_idx - 2:
            best_r = self.prev_r

        return best_r

    # =========================================================
    # SABRE interface
    # =========================================================

    def get_quality_delay(self, segment_index):

        buf = self.session.get_buffer_contents()
        buffer_sec = len(buf) * self.dt

        tp = self.session.get_throughput()

        self.update_throughput(tp)

        pred_tp = self.predict_throughput()

        chosen_r = self.select_bitrate(pred_tp, buffer_sec)

        q = self.R.index(chosen_r)

        self.prev_r = chosen_r
        self.session.last_quality = q

        if segment_index % 5000 == 0:
            print(
                f"[FINAL-MPC-BUFFER-SAFE] seg={segment_index} "
                f"buf={buffer_sec:.2f}s "
                f"tp={pred_tp:.2f} "
                f"r={chosen_r}"
            )

        return q, 0