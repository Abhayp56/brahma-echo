import { IMetricsService } from './types';
import { SystemMetricData } from '../types/arya';

class MockMetricsService implements IMetricsService {
  private currentMetrics: SystemMetricData = {
    cpuUsage: 24,
    ramUsage: 48,
    ramUsedGB: 15.3,
    ramTotalGB: 32.0,
    diskUsage: 62,
    diskUsedGB: 620,
    diskTotalGB: 1000,
    neuralLinkHealth: 'optimal',
    networkHealth: 'optimal',
    latencyMs: 14,
  };

  subscribeMetrics(callback: (metrics: SystemMetricData) => void): () => void {
    // Initial emit
    callback({ ...this.currentMetrics });

    const interval = setInterval(() => {
      // Simulate live fluctuate CPU (12% - 42%), RAM (45% - 54%), Latency (8 - 24 ms)
      const cpuNoise = Math.floor(Math.sin(Date.now() / 1500) * 12 + 28);
      const ramNoise = Math.floor(Math.cos(Date.now() / 3000) * 4 + 48);
      const latencyNoise = Math.floor(Math.sin(Date.now() / 800) * 6 + 14);

      this.currentMetrics = {
        ...this.currentMetrics,
        cpuUsage: Math.max(8, Math.min(98, cpuNoise)),
        ramUsage: Math.max(20, Math.min(95, ramNoise)),
        ramUsedGB: parseFloat(((ramNoise / 100) * 32.0).toFixed(1)),
        latencyMs: Math.max(5, Math.min(120, latencyNoise)),
      };

      callback({ ...this.currentMetrics });
    }, 2000);

    return () => clearInterval(interval);
  }
}

export const metricsService = new MockMetricsService();
