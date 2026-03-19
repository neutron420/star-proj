import pandas as pd
import numpy as np
import datetime

def generate_sample_data(num_points=100):
    now = datetime.datetime.now()
    timestamps = [now - datetime.timedelta(minutes=i) for i in range(num_points)]
    timestamps.reverse()
    
    # Base usage + some sine wave periodicity + random spikes
    base = 200
    amplitude = 100
    noise = np.random.normal(0, 10, num_points)
    
    # Create a trend to test prediction
    trend = np.linspace(0, 200, num_points)
    
    values = base + amplitude * np.sin(np.linspace(0, 4*np.pi, num_points)) + noise + trend
    
    # Add a huge spike at the end
    values[-5:] = values[-5:] * 2
    
    df = pd.DataFrame({
        'timestamp': timestamps,
        'usage_mb': values
    })
    return df

if __name__ == "__main__":
    df = generate_sample_data()
    df.to_csv("memory_usage_sample.csv", index=False)
    print("Generated memory_usage_sample.csv with 100 data points.")
