import time
import logging
import datetime
import numpy as np
import pandas as pd
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect
from sklearn.linear_model import LinearRegression
from prometheus_client import start_http_server, Gauge, Counter
import pytz

# --- Configuration & Hyperparameters ---
PROMETHEUS_URL = "http://prometheus-service.monitoring.svc.cluster.local:9090"
NAMESPACE = "default"
TARGET_DEPLOYMENT = "sample-app"

# Global Constants
MIN_MEMORY_MB = 128
MAX_MEMORY_MB = 4096
COOLDOWN_SECONDS = 90  # Shorter for V2.5 agility
PEAK_HOURS = (18, 23)

# --- Workload Types ---
WORKLOAD_STEADY = 0
WORKLOAD_TRENDING = 1
WORKLOAD_VOLATILE = 2

# --- Observability Metrics V2.5 ---
GAUGE_SCORE = Gauge('evmm_v25_scaling_score', 'Weighted scaling decision score')
GAUGE_CONFIDENCE = Gauge('evmm_v25_prediction_confidence', 'Confidence of current prediction (0-1)')
GAUGE_WORKLOAD_TYPE = Gauge('evmm_v25_workload_type', '0=Steady, 1=Trending, 2=Volatile')
GAUGE_SAVINGS_MB_HR = Gauge('evmm_v25_cost_savings_mb_hr', 'Total MB-Hours saved vs Max Limit')
GAUGE_ROC = Gauge('evmm_v25_memory_rate_of_change', 'Current rate of change (MB/s)')
GAUGE_USAGE = Gauge('evmm_v25_memory_usage_mb', 'Current memory usage in MB')
GAUGE_LIMIT = Gauge('evmm_v25_memory_limit_mb', 'Current limit in MB')
COUNTER_PANIC = Counter('evmm_v25_panic_scale_events', 'Total OOM-Guard panic reactions')

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
logger = logging.getLogger("COGNITIVE-EVMM-V2.5")

class WorkloadClassifier:
    """The 'Brain' - Classifies the workload to change strategy dynamically"""
    def __init__(self, history_limit=20):
        self.history_limit = history_limit

    def classify(self, history):
        if len(history) < 10: return WORKLOAD_STEADY
        
        vals = np.array([h[1] for h in history])
        roc_vals = np.diff(vals)
        
        # 1. Volatility check (Standard Deviation of ROC)
        volatility = np.std(roc_vals) / (np.mean(vals) + 1)
        if volatility > 0.05: # High fluctuation
            return WORKLOAD_VOLATILE
        
        # 2. Trending check (R-squared of linear fit)
        X = np.arange(len(vals)).reshape(-1, 1)
        model = LinearRegression().fit(X, vals)
        r_sq = model.score(X, vals)
        if r_sq > 0.8: # Strong direction
            return WORKLOAD_TRENDING
            
        return WORKLOAD_STEADY

class CostTracker:
    """Calculates research-level cost-efficiency metrics"""
    def __init__(self):
        self.total_savings_mb_sec = 0
        self.last_ts = time.time()

    def update(self, current_limit):
        now = time.time()
        dt = now - self.last_ts
        # Saving is (How much we COULD have spent (Max) - How much we are spending (Limit))
        savings = (MAX_MEMORY_MB - current_limit) * dt
        self.total_savings_mb_sec += savings
        self.last_ts = now
        # Convert to MB-Hour for display
        GAUGE_SAVINGS_MB_HR.set(self.total_savings_mb_sec / 3600)

class CognitiveDecisionEngine:
    """Adaptive weighted decision based on Workload Type"""
    def __init__(self):
        # Weights: [Usage, ROC, Trend]
        self.strategies = {
            WORKLOAD_STEADY: (0.7, 0.1, 0.2),   # Prioritize Usage (Cost Saving)
            WORKLOAD_TRENDING: (0.3, 0.1, 0.6), # Prioritize Trend (Prediction)
            WORKLOAD_VOLATILE: (0.4, 0.5, 0.1)  # Prioritize ROC (Safety)
        }

    def get_score(self, workload_type, usage_ratio, roc_norm, pred_ratio, confidence):
        w_usage, w_roc, w_trend = self.strategies[workload_type]
        
        # If low confidence, decrease trend weight and boost usage (fallback)
        if confidence < 0.5:
            w_trend *= confidence
            w_usage += (0.6 - w_trend)
            
        score = (w_usage * usage_ratio * 100 + 
                 w_roc * roc_norm * 100 + 
                 w_trend * pred_ratio * 100)
        
        # Peak Hour boost
        now = datetime.datetime.now(pytz.utc)
        if PEAK_HOURS[0] <= now.hour < PEAK_HOURS[1]:
            score *= 1.15
            
        return min(score, 100)

class HybridPredictor:
    def predict(self, history):
        if len(history) < 5: return None, 0.0
        df = pd.DataFrame(history, columns=['ts', 'val'])
        ema = df['val'].ewm(span=10).mean().iloc[-1]
        X = df[['ts']].values
        y = df['val'].values
        model = LinearRegression().fit(X, y)
        trend_pred = model.predict([[df['ts'].iloc[-1] + 120]])[0]
        prediction = max(ema + (model.coef_[0] * 120), 0)
        # R2 as confidence
        confidence = max(0, model.score(X, y))
        return prediction, confidence

class CognitiveEVMM:
    def __init__(self):
        try: config.load_incluster_config()
        except: config.load_kube_config()
        self.k8s = client.AppsV1Api()
        self.prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
        
        # Modules
        self.classifier = WorkloadClassifier()
        self.tracker = CostTracker()
        self.predictor = HybridPredictor()
        self.engine = CognitiveDecisionEngine()
        
        self.history = []
        self.last_scale_time = 0

    def get_metrics(self):
        query = f'sum(container_memory_working_set_bytes{{namespace="{NAMESPACE}", pod=~"{TARGET_DEPLOYMENT}-.*"}}) / 1024 / 1024'
        try:
            res = self.prom.custom_query(query)
            if res:
                v, ts = float(res[0]['value'][1]), float(res[0]['value'][0])
                self.history.append((ts, v))
                self.history = self.history[-60:]
                GAUGE_USAGE.set(v)
                return v, ts
        except: pass
        return None, None

    def run_cycle(self):
        usage, ts = self.get_metrics()
        if not usage: return

        # 1. Fetch Context
        dep = self.k8s.read_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE)
        lim_str = dep.spec.template.spec.containers[0].resources.limits.get('memory', '512Mi')
        current_limit = int(lim_str.replace('Mi', '')) if 'Mi' in lim_str else 512
        GAUGE_LIMIT.set(current_limit)
        self.tracker.update(current_limit)

        # 2. Analysis
        workload = self.classifier.classify(self.history)
        GAUGE_WORKLOAD_TYPE.set(workload)
        
        pred, conf = self.predictor.predict(self.history)
        GAUGE_CONFIDENCE.set(conf)
        
        roc = 0
        if len(self.history) >= 2:
            roc = (self.history[-1][1] - self.history[-2][1]) / (self.history[-1][0] - self.history[-2][0])
            GAUGE_ROC.set(roc)

        # 3. OOM GUARD (Panic Scale)
        if usage > (current_limit * 0.92):
            logger.warning("!!! PANIC SCALE INITIATED (OOM GUARD) !!!")
            COUNTER_PANIC.inc()
            self.apply_scale(current_limit, 2.0)
            return

        # 4. Cognitive Decision
        roc_norm = min(max(roc * 5, 0), 1) # Normalize ROC to 0-1
        score = self.engine.get_score(workload, usage/current_limit, roc_norm, (pred or usage)/current_limit, conf)
        GAUGE_SCORE.set(score)

        types = ["Steady", "Trending", "Volatile"]
        logger.info(f"[{types[workload]}] Score: {score:.1f} | Usage: {usage:.1f}Mi | ROC: {roc:.2f} | Conf: {conf:.2f}")

        # 5. Scaling
        step = 1.0
        if score > 85: step = 1.5
        elif score > 70: step = 1.2
        elif score < 25: step = 0.6
        elif score < 40: step = 0.8
        
        if step != 1.0:
            self.apply_scale(current_limit, step)

    def apply_scale(self, current_limit, step):
        if time.time() - self.last_scale_time < COOLDOWN_SECONDS:
            return
        new_limit = int(current_limit * step)
        new_limit = max(MIN_MEMORY_MB, min(MAX_MEMORY_MB, new_limit))
        if new_limit == current_limit: return
        
        patch = {"spec": {"template": {"spec": {"containers": [{"name": "app", "resources": {"limits": {"memory": f"{new_limit}Mi"}, "requests": {"memory": f"{new_limit}Mi"}}}]}}}}
        try:
            self.k8s.patch_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE, patch)
            logger.info(f">> SCALED: {current_limit} -> {new_limit} (Score based)")
            self.last_scale_time = time.time()
        except Exception as e:
            logger.error(f"K8s Error: {e}")

if __name__ == "__main__":
    start_http_server(8000)
    logger.info("COGNITIVE EVMM V2.5 ONLINE. System is learning workload patterns...")
    v25 = CognitiveEVMM()
    while True:
        try: v25.run_cycle()
        except Exception as e: logger.error(f"Cycle Failure: {e}")
        time.sleep(10)
