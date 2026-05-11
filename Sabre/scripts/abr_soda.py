import sabre
import math


class abr_soda(sabre.Abr):

    """
    SODA-inspired Adaptive Bitrate Streaming Algorithm

    Features:
    - QoE-based bitrate optimization
    - Continuous-time buffer dynamics
    - EMA throughput prediction
    - Finite-horizon recursive search
    - Buffer-aware safety adaptation
    - Smooth bitrate switching
    """

    def __init__(self, config):
        super().__init__(config)

        manifest = self.session.manifest
        self.R = sorted(manifest.bitrates)

        seg_t = manifest.segment_time
        self.dt = seg_t / 1000.0 if seg_t > 100 else float(seg_t)

        # Buffer settings
        self.x_max = 20.0
        self.x_bar = 10.0

        # QoE weights
        self.beta = 0.12
        self.gamma = 0.6

        # Throughput EMA
        self.ema_alpha = 0.5
        self.tp_ema = None

        # Search depth (future horizon)
        self.search_depth = 3

        # Previous bitrate
        self.r_prev = self.R[0]

        # Penalty constants
        self.THROUGHPUT_PENALTY = 10
        self.LOW_BUFFER_PENALTY = 40
        self.PANIC_PENALTY = 100

    # =========================================================
    # Utility Functions
    # =========================================================

    def utility(self, r):
        return math.log(r)

    def buffer_penalty(self, x):

        # Strong penalty below target buffer
        if x <= self.x_bar:
            return (self.x_bar - x) ** 2

        # Mild penalty above target buffer
        return 0.05 * (x - self.x_bar) ** 2

    def switch_penalty(self, r, r_prev):
        return (math.log(r) - math.log(r_prev)) ** 2

    # =========================================================
    # Continuous-Time Buffer Evolution
    # =========================================================

    def next_buffer(self, x0, omega, r):

        """
        Continuous-time buffer dynamics:
        x(t+1) = x(t) + (omega * dt / r) - dt
        """

        x1 = x0 + (omega * self.dt / r) - self.dt

        return max(0.0, min(self.x_max, x1))

    # =========================================================
    # Throughput Prediction
    # =========================================================

    def update_ema(self, tp):

        if tp <= 0:
            return

        if self.tp_ema is None:
            self.tp_ema = tp
        else:
            self.tp_ema = (
                self.ema_alpha * tp +
                (1 - self.ema_alpha) * self.tp_ema
            )

    # =========================================================
    # Adaptive Safety Factor
    # =========================================================

    def safety_factor(self, x):

        if x < 6:
            return 0.60

        elif x < 10:
            return 0.75

        elif x < 15:
            return 0.85

        return 0.95

    # =========================================================
    # QoE Objective
    # =========================================================

    def objective(self, omega, x0, r, r_prev):

        x1 = self.next_buffer(x0, omega, r)

        obj = (
            - self.utility(r)
            + self.beta * self.buffer_penalty(x1)
            + self.gamma * self.switch_penalty(r, r_prev)
        )

        safe = self.safety_factor(x0)

        # Soft throughput constraint
        if omega > 0 and r > safe * omega:
            obj += (
                self.THROUGHPUT_PENALTY *
                (r / (safe * omega))
            )

        # Low buffer protection
        if x1 < 6:
            obj += (
                self.LOW_BUFFER_PENALTY *
                (6 - x1)
            )

        # Panic mode
        if x0 < 4:
            obj += (
                self.PANIC_PENALTY *
                (r / self.R[0])
            )

        return obj, x1

    # =========================================================
    # Recursive Finite-Horizon Search
    # =========================================================

    def search(self, omega, x0, r_prev, depth):

        if depth == 0:
            return 0.0

        best_cost = float("inf")

        for r in self.R:

            obj, x1 = self.objective(
                omega,
                x0,
                r,
                r_prev
            )

            # Avoid invalid future states
            if x1 <= 0:
                continue

            future_cost = self.search(
                omega,
                x1,
                r,
                depth - 1
            )

            total_cost = obj + future_cost

            if total_cost < best_cost:
                best_cost = total_cost

        return best_cost

    # =========================================================
    # Bitrate Selection
    # =========================================================

    def select_bitrate(self, omega_hat, x0):

        best_r = self.R[0]
        best_total = float("inf")

        for r in self.R:

            obj, x1 = self.objective(
                omega_hat,
                x0,
                r,
                self.r_prev
            )

            if x1 <= 0:
                continue

            future_cost = self.search(
                omega_hat,
                x1,
                r,
                self.search_depth - 1
            )

            total = obj + future_cost

            if total < best_total:
                best_total = total
                best_r = r

        return best_r

    # =========================================================
    # Main ABR Interface
    # =========================================================

    def get_quality_delay(self, segment_index):

        # Current buffer occupancy
        buf = self.session.get_buffer_contents()
        x0 = len(buf) * self.dt

        # Throughput measurement
        tp = self.session.get_throughput()

        # Update EMA predictor
        self.update_ema(tp)

        omega_hat = (
            self.tp_ema
            if self.tp_ema
            else self.R[0]
        )

        # Select bitrate
        chosen_r = self.select_bitrate(
            omega_hat,
            x0
        )

        q = self.R.index(chosen_r)

        prev_r = self.r_prev
        self.r_prev = chosen_r

        self.session.last_quality = q

        
        return q, 0