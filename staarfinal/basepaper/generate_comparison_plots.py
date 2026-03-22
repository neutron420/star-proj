import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import warnings
warnings.filterwarnings('ignore')

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.linewidth'] = 1.2

np.random.seed(42)
t = np.linspace(0, 600, 600)

base_demand = 300 + 80 * np.sin(2 * np.pi * t / 200)
noise = np.random.normal(0, 15, len(t))
trend = np.where(t > 200, np.clip((t - 200) * 0.8, 0, 250), 0)

spike_component = np.zeros_like(t)
for i, ti in enumerate(t):
    if 350 < ti < 420:
        spike_component[i] = 500 * np.exp(-0.04 * abs(ti - 380))

workload_demand = base_demand + noise + trend + spike_component
workload_demand = np.clip(workload_demand, 100, 1800)

evmm_limit = np.zeros_like(t)
evmm_limit[0] = 512

for i in range(1, len(t)):
    current_limit = evmm_limit[i-1]
    usage = workload_demand[i]
    util = usage / current_limit if current_limit > 0 else 1.0

    if i > 10:
        window = workload_demand[max(0, i-60):i]
        bin_size = 10
        num_bins = len(window) // bin_size
        if num_bins >= 2:
            bin_avgs = [np.mean(window[b*bin_size:(b+1)*bin_size]) for b in range(num_bins)]
            scale_up = 0
            for b in range(1, len(bin_avgs)):
                g = bin_avgs[b] - bin_avgs[b-1]
                if g > 0:
                    scale_up += 6 * (0.8 ** b) * g
        else:
            scale_up = 0
    else:
        scale_up = 0

    if util > 0.80:
        new_limit = current_limit + max(scale_up * 0.15, 20)
    elif util < 0.70 and i > 10:
        new_limit = max(usage / 0.75, 200)
    else:
        new_limit = current_limit

    new_limit = np.clip(new_limit, 200, 2000)
    if abs(new_limit - current_limit) < 5:
        new_limit = current_limit
    evmm_limit[i] = evmm_limit[i-1] + 0.08 * (new_limit - evmm_limit[i-1])

cog_limit = np.zeros_like(t)
cog_limit[0] = 512
cog_state = []
ema = workload_demand[0]

for i in range(1, len(t)):
    current_limit = cog_limit[i-1]
    usage = workload_demand[i]
    util = usage / current_limit if current_limit > 0 else 1.0
    ema = 0.3 * usage + 0.7 * ema

    if i > 5:
        window = workload_demand[max(0, i-30):i]
        x = np.arange(len(window))
        if len(x) > 2:
            coeffs = np.polyfit(x, window, 1)
            slope = coeffs[0]
            y_pred = np.polyval(coeffs, x)
            ss_res = np.sum((window - y_pred) ** 2)
            ss_tot = np.sum((window - np.mean(window)) ** 2)
            r2 = max(0, 1 - ss_res / ss_tot) if ss_tot > 0 else 0
        else:
            slope, r2 = 0, 0
        roc = usage - workload_demand[i-1]
        variance = np.var(window) / (np.mean(window) ** 2) if np.mean(window) > 0 else 0
    else:
        slope, r2, roc, variance = 0, 0, 0, 0

    if abs(roc) > 30:
        state = "volatile"
    elif variance < 0.05 and r2 < 0.6:
        state = "steady"
    elif r2 >= 0.6 and slope > 0:
        state = "trending"
    else:
        state = "volatile"
    cog_state.append(state)

    if util > 0.92 or abs(roc) > 50:
        new_limit = min(2.0 * current_limit, 2000)
    else:
        trend_forecast = usage + 12 * slope
        hybrid = 0.4 * ema + 0.6 * trend_forecast
        if state == "steady":
            score = 0.50*util + 0.10*min(abs(roc)/100,1) + 0.20*r2*(hybrid/current_limit) + 0.20*util
        elif state == "trending":
            score = 0.20*util + 0.10*min(abs(roc)/100,1) + 0.50*r2*(hybrid/current_limit) + 0.20*util
        else:
            score = 0.15*util + 0.45*min(abs(roc)/100,1) + 0.15*r2*(hybrid/current_limit) + 0.25*util

        if score > 0.85: scale = 1.5
        elif score > 0.70: scale = 1.2
        elif score < 0.25: scale = 0.6
        elif score < 0.40: scale = 0.8
        else: scale = 1.0
        new_limit = np.clip(scale * current_limit, 128, 2000)

    cog_limit[i] = cog_limit[i-1] + 0.15 * (new_limit - cog_limit[i-1])

slack_evmm = np.clip(evmm_limit - workload_demand, 0, None)
slack_cog = np.clip(cog_limit - workload_demand, 0, None)

# =====================================================
# PLOT 1: BASE EVMM
# =====================================================
fig1, axes1 = plt.subplots(3, 1, figsize=(14, 11), gridspec_kw={'height_ratios': [3, 1.2, 1.2]})
fig1.patch.set_facecolor('white')

ax = axes1[0]
ax.set_facecolor('#fafafa')
ax.fill_between(t, workload_demand, alpha=0.12, color='#1976D2')
ax.plot(t, workload_demand, color='#1976D2', linewidth=1.8, alpha=0.85, label='Workload Memory Demand')
ax.plot(t, evmm_limit, color='#E65100', linewidth=2.8, label='EVMM Memory Limit')

danger_mask = workload_demand > evmm_limit * 0.95
ax.fill_between(t, workload_demand, evmm_limit, where=danger_mask, alpha=0.25, color='#D32F2F', label='Danger Zone (>95%)')
ax.fill_between(t, workload_demand, evmm_limit, where=(evmm_limit > workload_demand), alpha=0.06, color='#E65100')

spike_start = 350
reaction_candidates = np.where((t > spike_start) & (evmm_limit > workload_demand * 1.05))[0]
if len(reaction_candidates) > 0:
    ri = reaction_candidates[0]
    delay = int(t[ri] - spike_start)
    ax.annotate(f'Reaction Delay\n~{delay}s',
                xy=(t[ri], evmm_limit[ri]),
                xytext=(t[ri]+40, evmm_limit[ri]+180),
                fontsize=11, color='#C62828', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#C62828', lw=2.2),
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFF3E0', edgecolor='#E65100', alpha=0.95))

ax.axhline(y=512, color='#9E9E9E', linestyle='--', alpha=0.5, linewidth=1)
ax.text(8, 525, 'Initial Limit (512 MiB)', color='#757575', fontsize=9)

ax.set_title('Base EVMM Algorithm — Elastic Vertical Memory Management\n(Kang & Yu, SAC \'25 — Implemented in Go)',
              fontsize=16, fontweight='bold', color='#BF360C', pad=15)
ax.set_ylabel('Memory (MiB)', fontsize=12, color='#333333')
ax.legend(loc='upper left', fontsize=10, framealpha=0.95, facecolor='white', edgecolor='#BDBDBD')
ax.set_xlim(0, 600)
ax.set_ylim(0, 1500)
ax.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax.spines[spine].set_color('#BDBDBD')
ax.grid(True, alpha=0.2, color='#9E9E9E')

ax2 = axes1[1]
ax2.set_facecolor('#fafafa')
ax2.fill_between(t, slack_evmm, alpha=0.35, color='#FF8A65')
ax2.plot(t, slack_evmm, color='#E65100', linewidth=1.5)
ax2.axhline(y=np.mean(slack_evmm), color='#C62828', linestyle='--', linewidth=1.8)
ax2.text(500, np.mean(slack_evmm)+12, f'Avg Slack: {np.mean(slack_evmm):.0f} MiB',
         color='#C62828', fontsize=11, fontweight='bold')
ax2.set_ylabel('Memory Slack\n(MiB Wasted)', fontsize=10, color='#333333')
ax2.set_ylim(0, max(slack_evmm)*1.3)
ax2.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax2.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax2.spines[spine].set_color('#BDBDBD')
ax2.grid(True, alpha=0.2, color='#9E9E9E')

ax3 = axes1[2]
ax3.set_facecolor('#fafafa')
util_evmm = np.clip(workload_demand / np.maximum(evmm_limit, 1), 0, 1.2)
bar_colors = ['#D32F2F' if u > 0.92 else '#F9A825' if u > 0.80 else '#43A047' for u in util_evmm]
ax3.bar(t[::3], util_evmm[::3], width=3,
        color=[bar_colors[i] for i in range(0, len(t), 3)], alpha=0.75)
ax3.axhline(y=0.80, color='#F57F17', linestyle='--', linewidth=1.5, label='Scale-Up (80%) — Fixed')
ax3.axhline(y=0.70, color='#2E7D32', linestyle='--', linewidth=1.5, label='Scale-Down (70%) — Fixed')
ax3.axhline(y=0.95, color='#C62828', linestyle='--', linewidth=1.5, label='Container Stop (95%)')
ax3.set_ylabel('Utilization\nRatio', fontsize=10, color='#333333')
ax3.set_xlabel('Time (seconds)', fontsize=12, color='#333333')
ax3.set_ylim(0, 1.1)
ax3.legend(loc='upper right', fontsize=8, framealpha=0.95, facecolor='white', edgecolor='#BDBDBD', ncol=3)
ax3.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax3.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax3.spines[spine].set_color('#BDBDBD')
ax3.grid(True, alpha=0.2, color='#9E9E9E')

info = (
    "Language: Go  |  Runtime: CRI-O v1.27 + CRIU  |  Thresholds: Fixed (80% / 70%)\n"
    "Equations: (1)-(12)  |  Algorithms: 3 (Main Loop, ScaleUp, Remove)\n"
    f"Avg Slack: {np.mean(slack_evmm):.0f} MiB  |  "
    f"Peak Danger Intervals: {np.sum(workload_demand > evmm_limit * 0.92)}  |  "
    f"Priority: FEFP + Penalty + Reward"
)
fig1.text(0.5, 0.005, info, ha='center', fontsize=9, color='#616161',
         style='italic', family='monospace',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='#FFF3E0', edgecolor='#E65100', alpha=0.9))

plt.tight_layout(rect=[0, 0.06, 1, 1])
plt.savefig(r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\plot_base_evmm_algorithm.png',
            dpi=200, facecolor='white', bbox_inches='tight', pad_inches=0.3)
plt.close()
print("Plot 1 saved: plot_base_evmm_algorithm.png")


# =====================================================
# PLOT 2: COGNITIVE-EVMM
# =====================================================
fig2, axes2 = plt.subplots(3, 1, figsize=(14, 11), gridspec_kw={'height_ratios': [3, 1.2, 1.2]})
fig2.patch.set_facecolor('white')

ax4 = axes2[0]
ax4.set_facecolor('#fafafa')
ax4.fill_between(t, workload_demand, alpha=0.12, color='#1976D2')
ax4.plot(t, workload_demand, color='#1976D2', linewidth=1.8, alpha=0.85, label='Workload Memory Demand')
ax4.plot(t, cog_limit, color='#2E7D32', linewidth=2.8, label='Cognitive-EVMM Limit')

state_colors_bg = {'steady': '#C8E6C9', 'trending': '#E1BEE7', 'volatile': '#FFCDD2'}
padded_state = ['steady'] + cog_state
for i in range(len(t)-1):
    ax4.axvspan(t[i], t[i+1], alpha=0.15, color=state_colors_bg.get(padded_state[i], '#C8E6C9'))

danger_cog = workload_demand > cog_limit * 0.95
if np.any(danger_cog):
    ax4.fill_between(t, workload_demand, cog_limit, where=danger_cog, alpha=0.25, color='#D32F2F', label='Danger Zone')

panic_points = [i for i in range(1, len(t)) if cog_limit[i] > 0 and workload_demand[i]/cog_limit[i] > 0.92]
if panic_points:
    fp = panic_points[0]
    ax4.annotate('OOM-Guard\nPanic Scale!',
                xy=(t[fp], cog_limit[fp]),
                xytext=(t[fp]+50, cog_limit[fp]+220),
                fontsize=11, color='#C62828', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#C62828', lw=2.2),
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFEBEE', edgecolor='#C62828', alpha=0.95))

steady_p = mpatches.Patch(color='#4CAF50', alpha=0.35, label='Steady Mode')
trending_p = mpatches.Patch(color='#9C27B0', alpha=0.35, label='Trending Mode')
volatile_p = mpatches.Patch(color='#F44336', alpha=0.35, label='Volatile Mode')

ax4.axhline(y=512, color='#9E9E9E', linestyle='--', alpha=0.5, linewidth=1)
ax4.text(8, 525, 'Initial Limit (512 MiB)', color='#757575', fontsize=9)

handles, labels = ax4.get_legend_handles_labels()
handles.extend([steady_p, trending_p, volatile_p])
ax4.legend(handles=handles, loc='upper left', fontsize=9, framealpha=0.95,
          facecolor='white', edgecolor='#BDBDBD', ncol=2)

ax4.set_title('Cognitive-EVMM Algorithm — Cognitive Elastic Vertical Memory Management\n(Ritesh Kumar Singh, STAAR 2026 — Implemented in Python)',
              fontsize=16, fontweight='bold', color='#1B5E20', pad=15)
ax4.set_ylabel('Memory (MiB)', fontsize=12, color='#333333')
ax4.set_xlim(0, 600)
ax4.set_ylim(0, 1500)
ax4.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax4.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax4.spines[spine].set_color('#BDBDBD')
ax4.grid(True, alpha=0.2, color='#9E9E9E')

ax5 = axes2[1]
ax5.set_facecolor('#fafafa')
ax5.fill_between(t, slack_cog, alpha=0.35, color='#81C784')
ax5.plot(t, slack_cog, color='#2E7D32', linewidth=1.5)
ax5.axhline(y=np.mean(slack_cog), color='#1B5E20', linestyle='--', linewidth=1.8)
ax5.text(500, np.mean(slack_cog)+12, f'Avg Slack: {np.mean(slack_cog):.0f} MiB',
         color='#1B5E20', fontsize=11, fontweight='bold')
ax5.set_ylabel('Memory Slack\n(MiB Wasted)', fontsize=10, color='#333333')
ax5.set_ylim(0, max(max(slack_cog), max(slack_evmm))*1.3)
ax5.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax5.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax5.spines[spine].set_color('#BDBDBD')
ax5.grid(True, alpha=0.2, color='#9E9E9E')

ax6 = axes2[2]
ax6.set_facecolor('#fafafa')
state_y_map = {'steady': 0.33, 'trending': 0.66, 'volatile': 1.0}
state_c_map = {'steady': '#4CAF50', 'trending': '#9C27B0', 'volatile': '#F44336'}
state_y = [state_y_map[s] for s in padded_state]
state_c = [state_c_map[s] for s in padded_state]

ax6.bar(t[::2], [state_y[i] for i in range(0, len(t), 2)], width=2,
       color=[state_c[i] for i in range(0, len(t), 2)], alpha=0.7)
ax6.set_yticks([0.33, 0.66, 1.0])
ax6.set_yticklabels(['Steady', 'Trending', 'Volatile'], fontsize=10, color='#333333')
ax6.set_ylabel('Workload\nState', fontsize=10, color='#333333')
ax6.set_xlabel('Time (seconds)', fontsize=12, color='#333333')
ax6.set_ylim(0, 1.15)
ax6.tick_params(colors='#555555')
for spine in ['top', 'right']:
    ax6.spines[spine].set_visible(False)
for spine in ['bottom', 'left']:
    ax6.spines[spine].set_color('#BDBDBD')
ax6.grid(True, alpha=0.2, color='#9E9E9E', axis='x')

sc = sum(1 for s in cog_state if s == 'steady')
tc = sum(1 for s in cog_state if s == 'trending')
vc = sum(1 for s in cog_state if s == 'volatile')

info2 = (
    "Language: Python 3.9  |  Runtime: Kubernetes + Prometheus  |  Thresholds: Adaptive\n"
    "Equations: (1)-(17)  |  Modules: Monitor → Predict → Classify → Decide → Scale\n"
    f"Avg Slack: {np.mean(slack_cog):.0f} MiB  |  "
    f"States: {sc} steady / {tc} trending / {vc} volatile  |  "
    f"Panics: {len(panic_points)}"
)
fig2.text(0.5, 0.005, info2, ha='center', fontsize=9, color='#616161',
         style='italic', family='monospace',
         bbox=dict(boxstyle='round,pad=0.5', facecolor='#E8F5E9', edgecolor='#2E7D32', alpha=0.9))

plt.tight_layout(rect=[0, 0.06, 1, 1])
plt.savefig(r'c:\Users\R.K Singh\Desktop\star-proj\staarfinal\basepaper\plot_cognitive_evmm_algorithm.png',
            dpi=200, facecolor='white', bbox_inches='tight', pad_inches=0.3)
plt.close()
print("Plot 2 saved: plot_cognitive_evmm_algorithm.png")
print("Done!")
