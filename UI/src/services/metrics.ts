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

    

    return () => {};
  }
}

export const metricsService = new MockMetricsService();
