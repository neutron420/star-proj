import subprocess
import time

def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        # We strip both whitespace and literal single quotes
        return result.stdout.strip().replace("'", "").replace("\"", "")
    except Exception as e:
        return str(e)

print("🚀 Searching for sample-app pod...")
pod_name = run_command("kubectl get pods -l app=sample-app -o jsonpath='{.items[0].metadata.name}'")

if not pod_name or "Error" in pod_name:
    print("❌ Error: Sample app pod not found. Make sure it is running!")
    exit(1)

print(f"✅ Found pod: {pod_name}")
print("🔥 Injecting 800MB Memory Spike...")

# This python command inside the pod creates a large list to consume memory
spike_cmd = f"kubectl exec {pod_name} -- python3 -c \"import time; print('Allocating 800MB...'); x = [0] * (100 * 1024 * 1024); print('Success. Holding for 60s...'); time.sleep(60)\""

try:
    # Run in background so we don't block
    subprocess.Popen(spike_cmd, shell=True)
    print("\n⚡ SPIKE TRIGGERED!")
    print("👉 Watch your Autoscaler logs now to see the 'PANIC SCALE' reaction.")
except Exception as e:
    print(f"❌ Failed to trigger spike: {e}")
