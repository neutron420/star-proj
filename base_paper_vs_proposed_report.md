# 📄 Base Paper vs. Your Proposed Report — Full Context

---

## 🔬 The Base Paper: EVMM (Kang & Yu, 2025)

**Title:** *Elastic Vertical Memory Management for Container-based Stateful Applications in Kubernetes*  
**Authors:** Taeshin Kang & Heonchang Yu (Korea University)  
**Published:** SAC '25 (40th ACM/SIGAPP Symposium on Applied Computing), May 2025  
**Pages:** 9 pages

### What Problem Does It Solve?

Cloud containers in Kubernetes often **waste memory** because users over-provision to avoid crashes. The standard Kubernetes **Vertical Pod Autoscaler (VPA)** tries to fix this but has a critical flaw: **it restarts containers** whenever it changes their memory. For stateful applications (databases, ML jobs, scientific workflows), restarts mean **losing all progress** and starting from scratch.

### Core Idea

EVMM introduces **elastic vertical memory scaling without restarting containers**, specifically for Kubernetes environments where **swap memory is disabled** (the default).

### How It Works (4 Key Mechanisms)

| Mechanism | Description |
|-----------|-------------|
| **1. Task Priority Scoring** | Ranks containers by urgency using: CPU usage, memory usage, memory variance, node memory pressure, first-executed-first-priority (FEFP), penalty (for hogging scale-ups), and reward (for containers that were paused longest) |
| **2. Dynamic Scale Size** | Scale-up and scale-down amounts are computed based on memory usage **trends** over a time window (up to 60s), not fixed amounts |
| **3. CPU Throttling as Pause** | When memory is scarce, instead of killing containers, EVMM throttles their CPU to ~0.02 cores, effectively **pausing** them so they stop allocating more memory |
| **4. Checkpoint & Restore** | Uses Linux's CRIU to **checkpoint** paused containers and restore them later from the saved state, avoiding full restart |

### The 3 Algorithms

```
Algorithm 1: Main EVMM Loop
├── Scale-down underutilized containers
├── Identify scale-up candidates
├── Call Algorithm 2 (decide which get scale-up)
├── Call Algorithm 3 (decide which to checkpoint/remove)
└── Repair previously removed containers from checkpoints

Algorithm 2: DecisionScaleUp
├── Scale-up containers that fit in available node memory
├── Unpause containers that got scaled
└── Pause remaining candidates (CPU throttle)

Algorithm 3: DecisionRemove
├── Checkpoint containers above threshold
├── Handle restarted containers with checkpoint data
├── Remove containers when node memory > 95% threshold
└── Handle deadlock (too many paused vs running)
```

### Key Mathematical Equations

- **Resource Metric:** `R = [CPU_util, Mem_util, Node_Mem_util, Mem_variance] × W`
- **Priority Score:** `PS = [R, FEFP, Penalty, Reward] × W`
- **Scale-down:** `= MemLimit - (MemUsed / TargetUtil)`
- **Scale-up:** Sum of positive memory growth trends across 10s bins, weighted by `α`

### Experimental Results

| Metric | Result |
|--------|--------|
| Execution time reduction | Up to **35%** vs standard Kubernetes |
| Container restarts reduction | Up to **70x** fewer restarts |
| Memory utilization improvement | **1.5x** better than no oversubscription |
| Workloads tested | Blackscholes, Raytrace, Barnes, Radix (PARSEC/SPLASH-2x) |

### Identified Limitations (from the paper itself)

1. Container **skewing** — repaired containers can imbalance nodes
2. Checkpointing under memory pressure **overloads** the runtime
3. CPU throttling **can't always stop** highly volatile memory growth
4. Fixed thresholds across all workload phases

---

## 🧠 Your Proposed Report: Cognitive-EVMM

**Title:** *Cognitive Elastic Vertical Memory Management for Kubernetes-based Stateful Applications*  
**Author:** Ritesh Kumar Singh (Regd. No. 2301020845)  
**Supervisor:** Dr. Rakesh Kumar Ranjan  
**Institution:** C.V. Raman Global University, Bhubaneswar  
**Pages:** ~37 pages (STAAR report)

### What You Proposed

You took the EVMM base paper and built **Cognitive-EVMM** — an enhanced version that adds **intelligence** to the scaling decisions. The key insight: **different workload phases need different scaling strategies**, not one-size-fits-all.

### Your 5 Key Innovations Over EVMM

| # | Innovation | What It Does | Why EVMM Couldn't Do It |
|---|-----------|--------------|------------------------|
| 1 | **Cognitive Workload Classification** | Classifies each interval as **Steady**, **Trending**, or **Volatile** | EVMM uses same logic for all phases |
| 2 | **Hybrid Prediction Model** | Combines EMA (smoothing) + Linear Trend + R² Confidence | EVMM uses only trend-based scaling |
| 3 | **Adaptive Thresholds** | Scale-up/down thresholds change based on variance, node pressure, forecast confidence | EVMM uses fixed thresholds (80%/70%) |
| 4 | **Confidence-Aware Fallback** | When prediction confidence is low, controller trusts direct usage more than forecast | EVMM blindly follows predictions |
| 5 | **OOM-Guard Panic Path** | Emergency 2x scaling when usage > 92% of limit OR rate-of-change exceeds panic threshold | EVMM relies on CPU throttle which can fail |

### Your Architecture (4 Modules)

```
┌─────────────────────────────────────────────────────┐
│               COGNITIVE-EVMM PIPELINE               │
│                                                     │
│  ① Monitoring Module                                │
│     └── Prometheus → memory samples every 10s       │
│     └── Rolling history (60 samples ≈ 10 min)       │
│     └── Derives: usage ratio, ROC, variance         │
│                                                     │
│  ② Prediction Engine                                │
│     └── EMA (Exponential Moving Average)            │
│     └── Linear Trend + R² confidence                │
│     └── Hybrid forecast combining both              │
│                                                     │
│  ③ Cognitive Decision Engine ← YOUR KEY INNOVATION  │
│     └── Classifies: Steady / Trending / Volatile    │
│     └── Selects state-specific weight vectors       │
│     └── Computes cognitive decision score            │
│     └── Confidence-aware fallback                   │
│     └── OOM-guard panic check                       │
│                                                     │
│  ④ Scaling Controller                               │
│     └── In-place Kubernetes resize (no restart!)    │
│     └── Bounds: 128 MiB – 4096 MiB                 │
│     └── Cooldown: 90s anti-oscillation              │
│     └── Scale steps: 0.6, 0.8, 1.0, 1.2, 1.5, 2.0 │
└─────────────────────────────────────────────────────┘
```

### Your Key Equations

**Priority Score (improved over EVMM):**
```
P(t) = α·m̂(t) + β·ĉ(t) + γ·σ̂(t) + δ·ρ̂n(t) + η·ωi
```
*(memory pressure + CPU + variance + node pressure + service criticality)*

**Cognitive Decision Score:**
```
D(t) = wu·u(t) + wr·r̃(t) + wf·χ(t)·Û(t+H)/L(t) + wp·P(t)
```
*(usage + rate-of-change + confidence-weighted-forecast + priority)*

**Workload Classification:**
```
State = Steady   if σ̂ < τσ AND R² < τr
        Trending  if R² ≥ τr AND slope > 0  
        Volatile  otherwise OR |ROC| > τroc
```

**Adaptive Thresholds:**
```
θ↑(t) = θ₀↑ − a₁·σ̂(t) − a₂·ρ̂n(t) − a₃·[1−χ(t)]
θ↓(t) = θ₀↓ − b₁·[1−χ(t)] + b₂·[1−ρ̂n(t)]
```

### Your Experimental Results

| Metric | Standard VPA | Base EVMM | **Your Cognitive-EVMM** |
|--------|-------------|-----------|----------------------|
| Spike response latency | 240 s | 72 s | **12 s** ⚡ |
| Resource efficiency score | 48% | 62% | **84%** |
| Average memory slack | 210 MiB | 120 MiB | **78 MiB** |
| Scalability-reliability score | 45/100 | 65/100 | **96/100** |
| Balanced efficiency index | 0.57 | 0.71 | **0.92** |
| Memory waste vs EVMM | — | baseline | **~35% lower** |

---

## 🔄 Side-by-Side Comparison

| Aspect | Base EVMM (Kang & Yu) | Your Cognitive-EVMM |
|--------|----------------------|---------------------|
| **Scaling logic** | Single trend-based regime | 3 state-specific policies |
| **Thresholds** | Fixed (80% up, 70% down) | Adaptive (variance/pressure-aware) |
| **Prediction** | Memory usage trend over bins | Hybrid EMA + Linear + Confidence |
| **Workload awareness** | None | Steady/Trending/Volatile classification |
| **Emergency handling** | CPU throttling + checkpoint | OOM-Guard panic path (2x scaling) |
| **Forecast confidence** | Not considered | Explicitly modulates decisions |
| **Node pressure** | Implicit in memory checks | Explicit factor in priority + thresholds |
| **Platform** | Go, CRI-O, CRIU | Python, Prometheus, Kubernetes API |
| **Restart avoidance** | Via checkpoint/restore | Via in-place pod resize |
| **Spike response** | 72 s | 12 s (6x faster) |

---

## 🍕 Real-Life Example: A Food Delivery App During a Flash Sale

Let's make this super real. Imagine you're running a **Swiggy/Zomato-like food delivery platform** on Kubernetes. Your backend has a **Redis cache pod** (stateful — it holds live session data, restaurant menus, cart items, live order tracking for thousands of users). This Redis pod starts the day with **512 MB of memory**.

### The Scenario: Day in the Life

```
Timeline of your Redis pod's memory demand:

🕐 2:00 AM - 9:00 AM  │ ████░░░░░░░░░░░░ │ ~200 MB  (Night — quiet, few orders)
🕙 9:00 AM - 12:00 PM │ ████████░░░░░░░░ │ ~400 MB  (Morning — steady lunch browsing)
🕐 12:00 PM - 1:00 PM │ ██████████████░░ │ ~700 MB  (Lunch rush — gradual ramp-up)
⚡ 1:15 PM             │ ████████████████ │ 1800 MB! (FLASH SALE: "₹99 Thali" goes viral)
🕑 2:00 PM - 5:00 PM  │ ████████░░░░░░░░ │ ~400 MB  (Back to normal)
```

The **critical moment** is at **1:15 PM** — the marketing team drops a "₹99 Thali" flash sale notification to 5 million users. Orders explode. Redis needs to suddenly cache 10x more session/cart data.

If Redis **runs out of memory and crashes (OOM)**, here's what happens:
- 🔴 **50,000 live orders lose their tracking data**
- 🔴 **All user carts are wiped** — people have to re-add items
- 🔴 **Session tokens are gone** — everyone gets logged out
- 🔴 **It takes 3-5 minutes to restart and rebuild the cache** = massive revenue loss

So the question is: **how does each system handle this day?**

---

### ❌ What Happens with Standard VPA (Kubernetes Default)

```
 Memory
 2000 MB ┤
         │                              DEMAND ──→ ⚡💥 OOM KILL!
 1500 MB ┤                                    ╱
         │                                   ╱
 1000 MB ┤                                  ╱
         │                          ╭──────╯
  700 MB ┤                     ╭───╯
         │               ╭────╯
  512 MB ┤──── LIMIT ────────────────────────── (VPA hasn't changed it yet)
         │          ╭───╯
  200 MB ┤─────────╯
         └──────────────────────────────────────→ Time
         2AM     9AM    12PM   1:15PM  2PM
```

**What VPA does:**
1. **2 AM – 12 PM:** VPA watches. It collects historical data. It notices "hmm, usage is climbing." It *recommends* a new limit. But it hasn't applied anything yet — it works on long observation windows (hours).
2. **12:00 PM (Lunch rush):** Memory hits 700 MB, approaching the 512 MB limit. VPA's recommendation engine finally says "increase to 800 MB." But to apply this, **VPA evicts the pod and recreates it** with new limits.
   - 💀 **Redis restarts! All 20,000 active sessions are wiped.**
   - Takes 2 minutes to come back up and rebuild the cache from persistence.
3. **1:15 PM (Flash sale spike):** Memory rockets to 1800 MB. VPA is way too slow — its recommendation is still catching up. The pod was just recreated with 800 MB.
   - 💀💀 **OOM KILL! Redis crashes again.** 50,000 orders lose tracking.
   - VPA eventually recommends 2048 MB... after the damage is done.
4. **2:00 PM – 5:00 PM:** Everything is calm at 400 MB but the pod has 2048 MB allocated. **1648 MB is completely wasted** for hours.

> **Result:** 2 crashes, ~5 minutes total downtime, thousands of users affected, massive memory waste after the spike.

---

### ✅ What Happens with Base EVMM (The Base Paper's Solution)

```
 Memory
 2000 MB ┤
         │                              DEMAND ──→ ⚡
 1500 MB ┤                                    ╱  ╭── EVMM scales up
         │                                   ╱  ╱   (but 72 seconds late!)
 1000 MB ┤                                  ╱ ╱
         │                          ╭──────╯╱
  700 MB ┤── LIMIT tracks ────────╱───────╯
         │    demand ╭──── ╱─────╯
  512 MB ┤─────────╱╱────╯
         │        ╱╱
  200 MB ┤───────╯╱   (reclaims unused memory ✓)
         └──────────────────────────────────────→ Time
         2AM     9AM    12PM   1:15PM  2PM
```

**What EVMM does:**
1. **2 AM – 9 AM:** EVMM monitors every few seconds. Memory is ~200 MB, limit is 512 MB. EVMM sees low utilization (`200/512 = 39%`, below 70% threshold) → **scale-down!** Reclaims unused memory to ~300 MB limit. ✅ Memory saved!
2. **9 AM – 12 PM:** Memory climbs to 400 MB. EVMM detects the trend (each 10s bin shows increasing usage). It computes scale-up size from the trend equation and gradually raises the limit to ~550 MB. **No restart needed** — uses CPU throttle/checkpoint approach.
3. **12 PM (Lunch rush):** Memory ramps to 700 MB. EVMM scales up based on the trend. Limit goes to ~800 MB. Containers that can't get memory are **paused via CPU throttling** — their progress is saved, not lost. ✅
4. **1:15 PM (Flash sale 💥):** Memory **rockets to 1800 MB in seconds**. Here's the problem:
   - EVMM's trend-based prediction saw gradual growth. It expected maybe 900 MB next.
   - The **fixed threshold** (80%) triggers scale-up, but the system computes scale-up size from the **last 60 seconds of trends** — which shows moderate growth, not a spike.
   - ⚠️ **It takes ~72 seconds** to recognize the severity and scale up enough.
   - During those 72 seconds, some containers **hit their limits**. EVMM CPU-throttles them and checkpoints them. This saves their state (no data loss!), but...
   - For **highly volatile memory** (like Redis during a sudden spike), **CPU throttling doesn't stop memory from growing** — Redis is still receiving requests even at 0.02 CPU cores, and those requests still allocate memory.
   - ⚠️ Redis might still OOM during the 72-second gap if the spike is steep enough.
5. **2 PM – 5 PM:** EVMM gradually reclaims memory. But it uses **the same reclaim logic** it uses during spikes — so it's neither fast enough nor aggressive enough. Some waste lingers.

> **Result:** Much better! Maybe 0–1 crashes (vs 2 with VPA), state is checkpointed so recovery is fast. But the **72-second blind spot** during sudden spikes is dangerous, and memory reclamation after spikes is slow.

---

### 🧠✅ What Happens with YOUR Cognitive-EVMM

```
 Memory
 2000 MB ┤
         │                                    ⚡
 1500 MB ┤                              ╭─── PANIC SCALE ──╮ (within 12 seconds!)
         │                             ╱ DEMAND            │
 1000 MB ┤                            ╱                    │
         │                    ╭──────╯                     ╰── Smart reclaim
  700 MB ┤── LIMIT ──────── ╱── Trending mode                  (Steady mode)
         │    tight! ╭─── ╱─── (proactive)
  512 MB ┤─────────╱╱───╯
         │        ╱╱    Steady mode
  200 MB ┤───────╯╱     (efficiency-first)
         └──────────────────────────────────────→ Time
         2AM     9AM    12PM   1:15PM  2PM
```

**What Cognitive-EVMM does differently:**

1. **2 AM – 9 AM (Steady mode 😌):**
   - Classifier detects: low variance, weak trend → **"STEADY"**
   - Uses **efficiency-dominant weights**: `w = [0.5, 0.1, 0.2, 0.2]` (usage matters most)
   - Aggressively reclaims unused memory: limit drops to ~250 MB
   - **35% less waste** than EVMM during this calm period! 💰

2. **9 AM – 12 PM (Trending mode 📈):**
   - R² confidence is high, slope is positive → **"TRENDING"**
   - Switches to **forecast-dominant weights**: `w = [0.2, 0.1, 0.5, 0.2]`
   - The hybrid predictor (EMA + trend) forecasts demand 120 seconds ahead
   - **Proactively raises limit BEFORE** usage hits the threshold
   - At 11:45 AM, usage is 600 MB but Cognitive-EVMM already sets limit to 800 MB because it *predicts* 700 MB in 2 minutes. ✅ **Headroom is ready before it's needed!**

3. **12 PM – 1 PM (Still Trending):**
   - Keeps widening the headroom as the lunch ramp continues
   - Limit stays 100-150 MB ahead of usage at all times
   - **Zero risk of OOM** during the gradual ramp ✅

4. **1:15 PM (Flash Sale 💥 — Volatile mode 🚨):**
   - Memory jumps from 700 MB to 1100 MB in 10 seconds
   - Rate-of-change: `|ROC| = 40 MB/s` → exceeds `τ_panic` threshold
   - Classifier instantly switches to **"VOLATILE"** → **ROC-dominant weights**
   - **OOM-Guard triggers!** Usage/Limit ratio = `1100/900 = 0.92` → DANGER ZONE!
   - 🚨 **PANIC SCALING: Limit = 2 × 900 = 1800 MB** — applied in **12 seconds!**
   - No CPU throttling needed, no checkpoint needed — just **instant in-place resize**
   - Redis keeps running, all 50,000 orders stay intact ✅✅✅

5. **1:30 PM (Spike subsiding):**
   - Rate-of-change drops, variance decreases
   - Classifier switches back to **"TRENDING"** then **"STEADY"**
   - Confidence-aware fallback: prediction confidence was low during the spike (R² dropped), so the controller correctly **didn't trust the forecast** and used direct usage instead
   - Now in steady mode, it **efficiently reclaims** the extra memory
   - Within 15 minutes, limit drops from 1800 MB to ~500 MB — **no lingering waste!**

6. **2 PM – 5 PM (Steady mode again 😌):**
   - Tight tracking, minimal waste, limit hovers ~50 MB above usage
   - **78 MiB average slack** vs EVMM's 120 MiB ✅

> **Result:** Zero crashes, zero data loss, 12-second spike response, efficient memory use during calm periods, and smart reclamation after spikes. The controller behaved like 3 different controllers depending on the situation!

---

### 🎯 The Key Difference in One Picture

Think of it like **driving a car**:

| Situation | Standard VPA | Base EVMM | Your Cognitive-EVMM |
|-----------|-------------|-----------|---------------------|
| **Empty highway (night)** | Drives at 80 km/h always | Drives at 80 km/h always | Drives at **60 km/h** (saves fuel ⛽) |
| **Traffic building up** | Still 80, doesn't notice | Speeds up slightly following traffic | Checks GPS, sees jam ahead, **takes alternate route early** 🛣️ |
| **Sudden animal on road** | Sees too late, **crashes** 💥 | Brakes hard, skids, barely stops (72s) | Has **collision avoidance radar**, auto-brakes in **12s** 🛑 |
| **After the scare** | Still driving slow, wasting time | Slowly returns to normal speed | **Immediately back to efficient cruising** |

> 🚗 **VPA** = a car with no sensors, just a speedometer  
> 🚗 **EVMM** = a car with a rearview mirror (sees trends from the past)  
> 🚗 **Cognitive-EVMM** = a car with **radar + GPS + AI driving assistant** (reads the road, predicts, and reacts to the situation)

---

## 💡 In Simple Words

> **Base Paper (EVMM):** "We can avoid restarting containers by intelligently scaling memory up/down, pausing low-priority tasks via CPU throttling, and checkpointing them. It's way better than standard Kubernetes VPA."

> **Your Report (Cognitive-EVMM):** "EVMM is good, but it uses the same brain for all situations. We made it **smarter** — it now recognizes whether things are calm, ramping up, or spiking, and switches its strategy accordingly. It also knows when it's uncertain about predictions and plays it safe. The result: 6× faster reaction to spikes, 35% less wasted memory, and nearly perfect reliability."
