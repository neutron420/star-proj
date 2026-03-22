import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams['font.family'] = 'serif'
matplotlib.rcParams['font.size'] = 11

def make_table(data, col_widths, filename, title=None):
    n_rows = len(data)
    n_cols = len(data[0])
    row_h = 0.45
    fig_w = sum(col_widths) + 0.4
    fig_h = n_rows * row_h + (0.7 if title else 0.3)

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    fig.patch.set_facecolor('white')
    ax.set_xlim(0, fig_w)
    ax.set_ylim(0, fig_h)
    ax.axis('off')

    y_start = fig_h - (0.6 if title else 0.15)

    if title:
        ax.text(fig_w / 2, fig_h - 0.05, title, fontsize=14, fontweight='bold',
                fontfamily='serif', color='#1a1a1a', ha='center', va='top')

    col_starts = [0.2]
    for i in range(1, n_cols):
        col_starts.append(col_starts[-1] + col_widths[i-1])

    for row_idx, row in enumerate(data):
        ry = y_start - row_idx * row_h

        if row_idx == 0:
            bg = '#D4956A'
            tc = 'white'
            fw = 'bold'
            fs = 11.5
        elif row_idx % 2 == 1:
            bg = '#F5E6D8'
            tc = '#1a1a1a'
            fw = 'normal'
            fs = 10.5
        else:
            bg = '#FFFFFF'
            tc = '#1a1a1a'
            fw = 'normal'
            fs = 10.5

        for col_idx in range(n_cols):
            ax.add_patch(plt.Rectangle(
                (col_starts[col_idx], ry - row_h),
                col_widths[col_idx], row_h,
                facecolor=bg, edgecolor='#C0A080', linewidth=0.7
            ))
            ax.text(col_starts[col_idx] + 0.12, ry - row_h / 2,
                    row[col_idx], fontsize=fs, fontfamily='serif',
                    color=tc, fontweight=fw, va='center')

    plt.tight_layout(pad=0.1)
    plt.savefig(filename, dpi=200, facecolor='white', bbox_inches='tight', pad_inches=0.15)
    plt.close()
    print(f"Saved: {filename}")


# ============================================================
# TABLE 1: Cluster Environment Comparison
# ============================================================
make_table(
    data=[
        ['Component', 'Base EVMM (Kang & Yu, SAC \'25)', 'Cognitive-EVMM (Proposed)'],
        ['Language', 'Go', 'Python 3.9'],
        ['Cluster Setup', '4-node (1 master + 3 worker)', 'Kubernetes deployment + Prometheus'],
        ['Hardware', 'Intel i9-10900K, 32 GB RAM', 'Kubernetes-native container'],
        ['OS', 'Ubuntu 20.04', 'Container (Kubernetes pod)'],
        ['Network', '1 Gbps Ethernet', 'Cluster-internal networking'],
        ['Container Runtime', 'CRI-O v1.27 + CRIU', 'Kubernetes API (in-place resize)'],
        ['Kubernetes Version', 'v1.27', 'v1.27+ (InPlacePodVerticalScaling)'],
        ['Monitoring', 'CRI API (direct polling)', 'Prometheus (working_set_bytes)'],
        ['Visualization', 'Custom metrics', 'Grafana dashboards + Prometheus'],
    ],
    col_widths=[3.0, 4.5, 4.8],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_cluster_environment.png',
    title='Table 1: Cluster & Hardware Environment'
)


# ============================================================
# TABLE 2: Controller Parameters
# ============================================================
make_table(
    data=[
        ['Parameter', 'Base EVMM', 'Cognitive-EVMM', 'Impact'],
        ['Scale-Up Threshold', '80% (fixed)', 'Adaptive (θ₀ = 80%)', 'When to trigger upscaling'],
        ['Scale-Down Threshold', '70% (fixed)', 'Adaptive (θ₀ = 50%)', 'When to reclaim memory'],
        ['Danger / Stop Threshold', '95% (container stop)', '92% (OOM-Guard panic)', 'Emergency intervention'],
        ['CPU Pause Quota', '0.02 cores (throttle)', 'N/A (no throttling)', 'Paused container CPU'],
        ['Sampling Interval', 'Per-cycle monitoring', '10 seconds', 'Controller check frequency'],
        ['History Window', 'Tmax = 60 bins', '60 samples (~10 min)', 'Past data used for decisions'],
        ['Prediction Horizon', 'Trend within Tmax', '120 s lookahead', 'How far ahead it forecasts'],
        ['Cooldown Period', 'Not specified', '90 seconds', 'Anti-oscillation guard'],
        ['Memory Bounds', 'Not specified', '128 MiB – 4096 MiB', 'Hard safety limits'],
    ],
    col_widths=[3.2, 3.2, 3.5, 3.5],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_controller_parameters.png',
    title='Table 2: Controller Parameter Configuration'
)


# ============================================================
# TABLE 3: Test Workloads
# ============================================================
make_table(
    data=[
        ['Workload', 'Type', 'Parameters', 'Used By'],
        ['Blackscholes', 'Financial analysis', 'Volatility = 1.16', 'Base EVMM'],
        ['Raytrace', '3D rendering', 'Volatility = 1.68', 'Base EVMM'],
        ['Barnes', 'N-body astrophysics', 'Volatility = 1.37', 'Base EVMM'],
        ['Radix', 'Radix sort algorithm', 'Volatility = 2.65', 'Base EVMM'],
        ['Synthetic Mixed Trace', 'Sinusoidal + spike + trend', 'All 3 states combined', 'Cognitive-EVMM'],
        ['Live Spike Injection', '800–900 MiB burst', 'Latency & OOM testing', 'Cognitive-EVMM'],
    ],
    col_widths=[3.2, 3.2, 3.3, 2.8],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_test_workloads.png',
    title='Table 3: Experimental Workloads'
)


# ============================================================
# TABLE 4: Evaluation Metrics
# ============================================================
make_table(
    data=[
        ['Metric', 'Formula / Definition', 'What It Measures'],
        ['Memory Slack', 'S(t) = L(t) − U(t)', 'Gap between limit and usage (lower = efficient)'],
        ['Resource Waste', 'W = ∫₀ᵀ [L(t) − U(t)]⁺ dt', 'Cumulative wasted memory over time (MB-hours)'],
        ['OOM Safety Margin', 'M(t) = L(t) − U(t)', 'Distance from OOM kill (higher = safer)'],
        ['Scaling Latency', 'Time: spike start → headroom', 'Speed of reaction to demand spikes (seconds)'],
        ['Cost Savings Rate', 'CSR = (C_base − C_method) / C_base', 'Normalized memory cost reduction (%)'],
        ['Balanced Efficiency', 'BEI = 0.30E + 0.25S + 0.25R + 0.20Q', 'Composite: Efficiency + Safety + Response + Quality'],
    ],
    col_widths=[2.8, 4.5, 5.5],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_evaluation_metrics.png',
    title='Table 4: Evaluation Metrics'
)


# ============================================================
# TABLE 5: Key Results
# ============================================================
make_table(
    data=[
        ['Metric', 'Standard VPA', 'Base EVMM', 'Cognitive-EVMM', 'Improvement'],
        ['Spike Response Latency', '240 s', '72 s', '12 s', '6× faster'],
        ['Resource Efficiency', '48%', '62%', '84%', '+22% over EVMM'],
        ['Average Memory Slack', '210 MiB', '120 MiB', '78 MiB', '35% less waste'],
        ['Reliability Score', '45 / 100', '65 / 100', '96 / 100', '+31 points'],
        ['Balanced Efficiency Index', '0.57', '0.71', '0.92', '+0.21 over EVMM'],
        ['Burst Behavior', 'Late, stair-step', 'Faster but lagged', 'Early, state-aware', 'Best response'],
    ],
    col_widths=[3.0, 2.2, 2.5, 2.5, 2.8],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_key_results.png',
    title='Table 5: Headline Comparative Results'
)


# ============================================================
# TABLE 6: Systems Compared
# ============================================================
make_table(
    data=[
        ['Feature', 'Standard VPA', 'Base EVMM', 'Cognitive-EVMM'],
        ['Language', 'Go (Kubernetes)', 'Go', 'Python 3.9'],
        ['Thresholds', 'Fixed', 'Fixed (80%/70%)', 'Adaptive (context-aware)'],
        ['Prediction', 'Historical only', 'Trend bins (60s)', 'Hybrid EMA + Linear + R²'],
        ['Workload Awareness', 'None', 'Partial', 'Full (Steady/Trending/Volatile)'],
        ['Emergency Handling', 'Pod restart', 'CPU throttle + CRIU', 'OOM-Guard panic (2× scale)'],
        ['Forecast Confidence', 'Not used', 'Not used', 'R² modulates decisions'],
        ['Restart Required?', 'Yes (always)', 'Sometimes', 'Never (in-place resize)'],
        ['Equations Used', 'N/A', '12', '17'],
        ['Decision Modes', '1 (reactive)', '1 (trend-based)', '3 (state-specific weights)'],
    ],
    col_widths=[3.0, 2.8, 3.0, 3.8],
    filename=r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\table_systems_compared.png',
    title='Table 6: Feature-by-Feature Comparison'
)

print("\nAll 6 tables generated!")
