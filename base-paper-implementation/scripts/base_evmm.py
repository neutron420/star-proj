import time
import logging
import datetime
import numpy as np
import pandas as pd
from kubernetes import client, config
from prometheus_api_client import PrometheusConnect
import pytz

# --- ULTIMATE 2025 PAPER VERSION: Kang et al. ---
PROMETHEUS_URL = "http://prometheus-service.monitoring.svc.cluster.local:9090"
NAMESPACE = "default"
TARGET_DEPLOYMENT = "sample-app"

# Metadata Weights (Eq 5 & Eq 9)
WT_RESOURCE = [0.4, 0.4, 0.2] # Usage, CPU, Variance
WT_PRIORITY = [0.3, 0.2, 0.2, 0.3] # Resource, FEFP, Penalty, Reward

# Thresholds from Table 3
THR_SCALE_UP = 0.8
THR_SCALE_DOWN = 0.7
THR_STOP = 0.95
QUOTA_PAUSE = "20m"

logging.basicConfig(level=logging.INFO, format='%(asctime)s [PAPER-ULTIMATE] %(message)s')
logger = logging.getLogger("EVMM-ULTIMATE")

class UltimateEVMM:
    def __init__(self):
        try: config.load_incluster_config()
        except: config.load_kube_config()
        self.k8s_apps = client.AppsV1Api()
        self.prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
        
        self.history = []
        self.start_ts = time.time()
        self.scale_up_history = 0
        self.pause_time_total = 0 # Reward (Eq 8)
        self.is_paused = False
        self.last_pause_start = 0

    def get_metrics(self):
        query = f'sum(container_memory_working_set_bytes{{namespace="{NAMESPACE}", pod=~"{TARGET_DEPLOYMENT}-.*"}}) / 1024 / 1024'
        try:
            res = self.prom.custom_query(query)
            if res:
                v, ts = float(res[0]['value'][1]), float(res[0]['value'][0])
                self.history.append((ts, v))
                self.history = self.history[-7:] # 60s window
                return v
        except: pass
        return None

    def calculate_priority_score(self, usage_ratio):
        """Equation 9: PS = [R_ci, FEFP, Penalty, Reward] * WT"""
        # 1. Resource Metric (Eq 5)
        # Using simplified Variance (Eq 4)
        vals = [h[1] for h in self.history]
        variance = np.var(vals) if len(vals) > 1 else 0
        r_ci = (usage_ratio * WT_RESOURCE[0] + 0.1 * WT_RESOURCE[1] + (variance/100) * WT_RESOURCE[2])
        
        # 2. FEFP (Eq 6)
        fefp = 1 / (max(time.time() - self.start_ts, 1))
        
        # 3. Penalty (Eq 7)
        # Simplified: ratio of own scale-ups to a baseline node total (simulated as 10)
        penalty = 1 - (self.scale_up_history / 10) 
        
        # 4. Reward (Eq 8)
        reward = self.pause_time_total / (time.time() - self.start_ts)
        
        # Final Priority Score
        ps = (r_ci * WT_PRIORITY[0] + fefp * WT_PRIORITY[1] + penalty * WT_PRIORITY[2] + reward * WT_PRIORITY[3])
        return ps

    def run_cycle(self):
        usage = self.get_metrics()
        if not usage: return

        dep = self.k8s_apps.read_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE)
        lim_str = dep.spec.template.spec.containers[0].resources.limits.get('memory', '512Mi')
        current_limit = int(lim_str.replace('Mi', '')) if 'Mi' in lim_str else 512
        
        usage_ratio = usage / current_limit
        ps_score = self.calculate_priority_score(usage_ratio)
        
        logger.info(f"Monitor: Usage={usage:.1f}Mi | PriorityScore={ps_score:.4f}")

        # Algorithm 1: Scaling Logic
        if usage_ratio > THR_SCALE_UP:
            # Equation 11 Trend Scaling
            growth = sum([max(self.history[i][1] - self.history[i-1][1], 0) for i in range(1, len(self.history))])
            scale_step = max(growth * 1.5, 32)
            
            # Simulated node capacity check
            IF_NODE_READY = True 
            if IF_NODE_READY:
                new_limit = int(current_limit + scale_step)
                self.apply_patch(new_limit, "SCALE-UP")
                self.scale_up_history += 1
                if self.is_paused: self.unpause()
            else:
                self.pause()
        
        elif usage_ratio < THR_SCALE_DOWN:
            # Equation 10 reclaim
            new_limit = int(usage / 0.75) # Target 75%
            if new_limit < current_limit - 16:
                self.apply_patch(new_limit, "SCALE-DOWN")

        if usage_ratio > THR_STOP:
            logger.warning("!!! CRITICAL LIMIT REACHED (ContainerStop Policy) !!!")

    def pause(self):
        if not self.is_paused:
            patch = {"spec": {"template": {"spec": {"containers": [{"name": "app", "resources": {"limits": {"cpu": QUOTA_PAUSE}}}]}}}}
            self.k8s_apps.patch_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE, patch)
            self.last_pause_start = time.time()
            self.is_paused = True
            logger.warning("Container PAUSED (CPU Throttled)")

    def unpause(self):
        if self.is_paused:
            patch = {"spec": {"template": {"spec": {"containers": [{"name": "app", "resources": {"limits": {"cpu": "200m"}}}]}}}}
            self.k8s_apps.patch_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE, patch)
            self.pause_time_total += (time.time() - self.last_pause_start)
            self.is_paused = False
            logger.info("Container UNPAUSED")

    def apply_patch(self, new_limit, t):
        new_limit = max(128, min(4096, new_limit))
        patch = {"spec": {"template": {"spec": {"containers": [{"name": "app", "resources": {"limits": {"memory": f"{new_limit}Mi"}, "requests": {"memory": f"{new_limit}Mi"}}}]}}}}
        self.k8s_apps.patch_namespaced_deployment(TARGET_DEPLOYMENT, NAMESPACE, patch)
        logger.info(f">> {t}: New Limit {new_limit}Mi")

if __name__ == "__main__":
    uevmm = UltimateEVMM()
    while True:
        try: uevmm.run_cycle()
        except: pass
        time.sleep(10)
