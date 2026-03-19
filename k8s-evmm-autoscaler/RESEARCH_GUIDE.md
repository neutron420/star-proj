# COGNITIVE EVMM V2.5: Research Excellence Guide

This version represents a **Cognitive Improvement** over the standard Elastic Vertical Memory Management (EVMM) paper, introducing **Workload-Aware Specialization**.

## 1. The Innovation: Workload Classification
Most autoscalers use a single formula for all apps. Our system **Classifies** the workload every cycle and picks a specific scaling strategy:

| Workload Type | Detection Logic | Primary Strategy | Primary Goal |
| :--- | :--- | :--- | :--- |
| **Steady** | Low variance / Mean ratio | Usage-Centric (70% weight) | **Resource Savings** |
| **Trending** | High R-Squared (Linear Fit) | Prediction-Centric (60% weight) | **Proactive Response** |
| **Volatile** | High standard deviation of ROC | ROC-Centric (50% weight) | **Safety & OOM Prevention** |

---

## 2. Research Comparison Table (The "Money" Chart)

Use this table in your paper to show why this system is "Advanced":

| Feature | Standard K8s VPA | Base EVMM (Kang 25) | Our Cognitive V2.5 |
| :--- | :--- | :--- | :--- |
| **Scaling Trigger** | Threshold (Usage > 80%) | Periodic Re-evaluation | **Real-time Weighted Score** |
| **Prediction** | None (Reactive) | Simple Linear Regression | **Hybrid EMA + Trend Inference** |
| **Spike Response** | Waits for breach (Late) | Prediction-based (Better) | **Instant ROC (Emergency Panic)** |
| **Workload Awareness**| None | None | **Auto-Switching Strategies** |
| **Cost Metrics** | None | Resource Utilization % | **MB-Hour Savings Accumulator** |
| **Instability Fix** | None | Cooldown mechanism | **Confidence-Based Fallback** |

---

## 3. Evaluation: Mathematical Metric (RMSE vs. Saving)
In your evaluation section, measure the **Savings Efficiency ($SE$):**

$$SE = \frac{\int (MaxLimit - DynamicLimit) dt}{\text{OOM-Count} + 1}$$

- High $SE$ means you saved massive resources while keeping the app alive.
- **Hypothesis:** Because V2.5 uses "Steady" mode during nights and "Volatile" mode during spikes, it will achieve **30-40% higher $SE$** than the base EVMM approach.

## 4. Final Algorithm Pseudocode
```python
While True:
    Usage = GetFromPrometheus()
    Class = Classifier.Categorize(History) # STEADY, TRENDING, VOLATILE
    
    # Adaptive Weighting
    Weights = Map_Weights(Class)
    
    # Hybrid Prediction
    (Pred, Confidence) = Predictor.Forecast(History)
    
    # Decision Engine
    Score = Sum(Weights * [Usage, ROC, Pred*Confidence])
    
    # SLO OOM-Guard
    If Usage > 92% of Limit -> Force Scale 2.0x
    Else -> Scale_By_Score(Score)
    
    Update_Cost_Savings_Metric()
    Sleep(10s)
```
