import time
import math
import numpy as np
from collections import deque
from enum import Enum
from typing import Optional, Tuple
from dataclasses import dataclass, field


SAMPLING_INTERVAL   = 10
HISTORY_SIZE        = 60
PREDICTION_HORIZON  = 120
MIN_MEMORY_MIB      = 128
MAX_MEMORY_MIB      = 4096
COOLDOWN_SECONDS    = 90
DANGER_ZONE_THRESH  = 0.92
PANIC_ROC_THRESHOLD = 50.0
EMA_LAMBDA          = 0.3

TAU_SIGMA           = 0.05
TAU_R               = 0.6
TAU_ROC             = 30.0

THETA_UP_BASE       = 0.80
THETA_DOWN_BASE     = 0.50

A1, A2, A3          = 0.05, 0.05, 0.05
B1, B2              = 0.05, 0.05

ALPHA = 0.35
BETA  = 0.15
GAMMA = 0.20
DELTA = 0.20
ETA   = 0.10

TAU_85 = 0.85
TAU_70 = 0.70
TAU_40 = 0.40
TAU_25 = 0.25

KAPPA = 0.4


class WorkloadState(Enum):
    STEADY   = "steady"
    TRENDING = "trending"
    VOLATILE = "volatile"


STATE_WEIGHTS = {
    WorkloadState.STEADY:   {"w_u": 0.50, "w_r": 0.10, "w_f": 0.20, "w_p": 0.20},
    WorkloadState.TRENDING: {"w_u": 0.20, "w_r": 0.10, "w_f": 0.50, "w_p": 0.20},
    WorkloadState.VOLATILE: {"w_u": 0.15, "w_r": 0.45, "w_f": 0.15, "w_p": 0.25},
}


@dataclass
class PodMetrics:
    memory_usage_mib: float = 0.0
    memory_limit_mib: float = 256.0
    cpu_usage_ratio: float = 0.0
    node_mem_used_mib: float = 0.0
    node_mem_total_mib: float = 0.0
    service_criticality: float = 0.8
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_SIZE))


def compute_priority_score(metrics: PodMetrics, variance: float) -> float:
    mem_pressure = min(metrics.memory_usage_mib / max(metrics.memory_limit_mib, 1.0), 1.0)
    cpu_usage = min(metrics.cpu_usage_ratio, 1.0)
    norm_variance = min(variance, 1.0)
    node_pressure = 0.0
    if metrics.node_mem_total_mib > 0:
        node_pressure = min(metrics.node_mem_used_mib / metrics.node_mem_total_mib, 1.0)
    criticality = metrics.service_criticality

    priority = (
        ALPHA * mem_pressure +
        BETA  * cpu_usage +
        GAMMA * norm_variance +
        DELTA * node_pressure +
        ETA   * criticality
    )
    return priority


def compute_ema(history: list, lam: float = EMA_LAMBDA) -> float:
    if not history:
        return 0.0
    ema = history[0]
    for value in history[1:]:
        ema = lam * value + (1 - lam) * ema
    return ema


def linear_forecast(history: list, horizon: float = PREDICTION_HORIZON
                    ) -> Tuple[float, float, float]:
    n = len(history)
    if n < 3:
        return 0.0, 0.0, history[-1] if history else 0.0

    x = np.arange(n, dtype=float)
    y = np.array(history, dtype=float)

    x_mean = np.mean(x)
    y_mean = np.mean(y)
    ss_xy = np.sum((x - x_mean) * (y - y_mean))
    ss_xx = np.sum((x - x_mean) ** 2)

    if ss_xx == 0:
        return 0.0, 0.0, y_mean

    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean

    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y_mean) ** 2)
    r_squared = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    horizon_ticks = horizon / SAMPLING_INTERVAL
    current_usage = history[-1]
    trend_forecast = current_usage + horizon_ticks * slope

    return slope, r_squared, trend_forecast


def hybrid_forecast(ema_value: float, trend_value: float,
                    kappa: float = KAPPA) -> float:
    return kappa * ema_value + (1.0 - kappa) * trend_value


def adapt_thresholds(variance: float, node_pressure: float,
                     confidence: float) -> Tuple[float, float]:
    norm_var = min(variance, 1.0)
    norm_np = min(node_pressure, 1.0)
    norm_conf = min(max(confidence, 0.0), 1.0)

    theta_up = (THETA_UP_BASE
                - A1 * norm_var
                - A2 * norm_np
                - A3 * (1.0 - norm_conf))

    theta_down = (THETA_DOWN_BASE
                  - B1 * (1.0 - norm_conf)
                  + B2 * (1.0 - norm_np))

    return max(theta_up, 0.3), max(theta_down, 0.2)


def classify_workload(variance: float, rate_of_change: float,
                      r_squared: float, slope: float) -> WorkloadState:
    if abs(rate_of_change) > TAU_ROC:
        return WorkloadState.VOLATILE

    if variance < TAU_SIGMA and r_squared < TAU_R:
        return WorkloadState.STEADY

    if r_squared >= TAU_R and slope > 0:
        return WorkloadState.TRENDING

    return WorkloadState.VOLATILE


def cognitive_decision_score(
    utilization_ratio: float,
    normalized_roc: float,
    confidence: float,
    forecast_ratio: float,
    priority: float,
    state: WorkloadState
) -> float:
    w = STATE_WEIGHTS[state]
    effective_conf = max(confidence, 0.0)

    score = (
        w["w_u"] * utilization_ratio +
        w["w_r"] * normalized_roc +
        w["w_f"] * effective_conf * forecast_ratio +
        w["w_p"] * priority
    )
    return score


def map_score_to_scale(score: float) -> float:
    if score > TAU_85:
        return 1.5
    elif score > TAU_70:
        return 1.2
    elif score < TAU_25:
        return 0.6
    elif score < TAU_40:
        return 0.8
    else:
        return 1.0


def is_danger_zone(usage: float, limit: float, roc: float) -> bool:
    if limit <= 0:
        return True
    utilization = usage / limit
    near_limit = utilization > DANGER_ZONE_THRESH
    high_velocity = abs(roc) > PANIC_ROC_THRESHOLD
    return near_limit or high_velocity


def panic_scale(current_limit: float) -> float:
    return clip(2.0 * current_limit, MIN_MEMORY_MIB, MAX_MEMORY_MIB)


def clip(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(value, max_val))


def compute_new_limit(scale_factor: float, current_limit: float) -> float:
    return clip(scale_factor * current_limit, MIN_MEMORY_MIB, MAX_MEMORY_MIB)


def compute_variance(history: list) -> float:
    if len(history) < 2:
        return 0.0
    arr = np.array(history)
    mean = np.mean(arr)
    if mean == 0:
        return 0.0
    variance = np.var(arr)
    return variance / (mean ** 2)


def compute_rate_of_change(history: list) -> float:
    if len(history) < 2:
        return 0.0
    return history[-1] - history[-2]


def normalize_roc(roc: float, max_roc: float = 100.0) -> float:
    return min(abs(roc) / max_roc, 1.0)


class CognitiveEVMMController:

    def __init__(self, target_deployment: str, target_namespace: str = "default"):
        self.target_deployment = target_deployment
        self.target_namespace = target_namespace
        self.history: deque = deque(maxlen=HISTORY_SIZE)
        self.last_scale_time: float = 0.0
        self.panic_count: int = 0
        self.total_saved_mb_hours: float = 0.0
        self.is_active: bool = True

    def fetch_memory_usage(self) -> float:
        return 0.0

    def fetch_memory_limit(self) -> float:
        return 256.0

    def patch_kubernetes_resources(self, new_limit_mib: float):
        print(f"[PATCH] Setting memory limit to {new_limit_mib:.0f} MiB")

    def export_observability_metrics(self, state: WorkloadState, score: float,
                                      confidence: float, new_limit: float):
        state_map = {WorkloadState.STEADY: 0, WorkloadState.TRENDING: 1,
                     WorkloadState.VOLATILE: 2}
        print(f"[METRICS] State={state.value}, Score={score:.3f}, "
              f"Conf={confidence:.3f}, Limit={new_limit:.0f} MiB, "
              f"Panics={self.panic_count}")

    def run(self):
        print(f"[START] Cognitive-EVMM Controller for '{self.target_deployment}'")
        print(f"[CONFIG] Sampling={SAMPLING_INTERVAL}s, History={HISTORY_SIZE}, "
              f"Horizon={PREDICTION_HORIZON}s, Cooldown={COOLDOWN_SECONDS}s")
        print(f"[CONFIG] Memory bounds: [{MIN_MEMORY_MIB}, {MAX_MEMORY_MIB}] MiB")
        print(f"[CONFIG] Danger zone: >{DANGER_ZONE_THRESH*100}% or ROC>{PANIC_ROC_THRESHOLD}")

        while self.is_active:

            U_t = self.fetch_memory_usage()
            L_t = self.fetch_memory_limit()

            self.history.append(U_t)
            history_list = list(self.history)

            if len(history_list) < 3:
                time.sleep(SAMPLING_INTERVAL)
                continue

            r_t = compute_rate_of_change(history_list)
            sigma_t = compute_variance(history_list)

            metrics = PodMetrics(
                memory_usage_mib=U_t,
                memory_limit_mib=L_t,
                cpu_usage_ratio=0.5,
                node_mem_used_mib=0.0,
                node_mem_total_mib=0.0,
            )
            rho_t = 0.0
            if metrics.node_mem_total_mib > 0:
                rho_t = metrics.node_mem_used_mib / metrics.node_mem_total_mib

            P_t = compute_priority_score(metrics, sigma_t)

            EMA_t = compute_ema(history_list)

            slope, conf_t, trend_forecast = linear_forecast(
                history_list, PREDICTION_HORIZON
            )

            U_hat = hybrid_forecast(EMA_t, trend_forecast)

            state = classify_workload(sigma_t, r_t, conf_t, slope)

            if is_danger_zone(U_t, L_t, r_t):
                L_new = panic_scale(L_t)
                self.panic_count += 1
                score = 1.0
                print(f"[PANIC] Usage={U_t:.0f} MiB, Limit={L_t:.0f} MiB, "
                      f"ROC={r_t:.1f} -> PANIC to {L_new:.0f} MiB!")

            else:
                utilization_ratio = U_t / max(L_t, 1.0)
                norm_roc = normalize_roc(r_t)
                forecast_ratio = U_hat / max(L_t, 1.0)

                score = cognitive_decision_score(
                    utilization_ratio=utilization_ratio,
                    normalized_roc=norm_roc,
                    confidence=conf_t,
                    forecast_ratio=forecast_ratio,
                    priority=P_t,
                    state=state
                )

                theta_up, theta_down = adapt_thresholds(sigma_t, rho_t, conf_t)

                scale_factor = map_score_to_scale(score)

                L_new = compute_new_limit(scale_factor, L_t)

            cooldown_elapsed = (time.time() - self.last_scale_time) > COOLDOWN_SECONDS
            limit_changed = abs(L_new - L_t) > 1.0

            if cooldown_elapsed and limit_changed:
                self.patch_kubernetes_resources(L_new)
                self.last_scale_time = time.time()

                saved = (MAX_MEMORY_MIB - L_new) * (SAMPLING_INTERVAL / 3600.0)
                self.total_saved_mb_hours += saved

                self.export_observability_metrics(state, score, conf_t, L_new)

            time.sleep(SAMPLING_INTERVAL)


if __name__ == "__main__":
    controller = CognitiveEVMMController(
        target_deployment="sample-workload",
        target_namespace="default"
    )

    try:
        controller.run()
    except KeyboardInterrupt:
        print(f"\n[STOP] Controller terminated.")
        print(f"[STATS] Total panics: {controller.panic_count}")
        print(f"[STATS] Total saved: {controller.total_saved_mb_hours:.2f} MB-hours")
