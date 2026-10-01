import React, { useEffect, useState } from 'react';
import { Cpu, HardDrive, Zap, Network, Radio, ChevronDown, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { StatusDot } from '../ui/StatusDot';
import { useAryaStore } from '../../store/useAryaStore';
import { metricsService } from '../../services';

/**
 * SystemMetrics — Live telemetry panel.
 * When Desktop Agent is connected, metrics are streamed live via psutil over WebSocket.
 * When disconnected, renders graceful sample telemetry (neural links, cloud network, standby ping).
 */
export const SystemMetrics: React.FC = () => {
  const desktopAgentState = useAryaStore((s) => s.desktopAgentState);
  const metrics = useAryaStore((s) => s.metrics);
  const setMetrics = useAryaStore((s) => s.setMetrics);
  const [expanded, setExpanded] = useState(true);

  useEffect(() => {
    const unsubscribe = metricsService.subscribeMetrics((data) => {
      // Only set mock metrics if we don't already have real ones
      if (!metrics) {
        setMetrics(data);
      }
    });
    return () => unsubscribe();
  }, [setMetrics, metrics]);

  const isConnected = desktopAgentState.connected;

  // Real or fallback sample data
  const linkHealth: 'optimal' | 'degraded' | 'offline' = isConnected
    ? (metrics?.neuralLinkHealth || 'optimal')
    : 'degraded';
  const netHealth: 'optimal' | 'degraded' | 'offline' = metrics?.networkHealth || 'optimal';
  const pingDisplay = isConnected ? `${metrics?.latencyMs || 12}ms` : '32ms (Cloud)';
  const cpuPercent = isConnected ? (metrics?.cpuUsage || 0) : 18;
  const ramUsed = isConnected ? (metrics?.ramUsedGB || 0) : 8.2;
  const ramTotal = isConnected ? (metrics?.ramTotalGB || 0) : 16.0;
  const ramPercent = isConnected ? (metrics?.ramUsage || 0) : 51;
  const diskUsed = isConnected ? (metrics?.diskUsedGB || 0) : 320;
  const diskTotal = isConnected ? (metrics?.diskTotalGB || 0) : 512;
  const diskPercent = isConnected ? (metrics?.diskUsage || 0) : 62;

  return (
    <GlassCard
      title="System Metrics"
      icon={<Cpu className="w-4 h-4 text-white" />}
      action={
        <StatusDot
          status={isConnected ? 'optimal' : 'degraded'}
          label={isConnected ? 'LINKED' : 'STANDBY'}
          size="sm"
        />
      }
      className="w-full flex-shrink-0"
    >
      <div className="space-y-2">
        {/* Status Row: Neural Link, Network Mesh, Ping */}
        <div className="grid grid-cols-3 gap-1.5">
          <div className="glass-panel p-2 rounded-lg border-white/10 text-center relative overflow-hidden">
            <div className="flex items-center justify-center gap-1 text-[9px] font-mono text-zinc-400 mb-0.5">
              <Zap className="w-2.5 h-2.5 text-zinc-300" />
              <span>LINK</span>
            </div>
            <StatusDot
              status={linkHealth}
              label={isConnected ? 'ONLINE' : 'STANDBY'}
              size="sm"
              className="justify-center"
            />
          </div>

          <div className="glass-panel p-2 rounded-lg border-white/10 text-center relative overflow-hidden">
            <div className="flex items-center justify-center gap-1 text-[9px] font-mono text-zinc-400 mb-0.5">
              <Network className="w-2.5 h-2.5 text-zinc-300" />
              <span>NET</span>
            </div>
            <StatusDot
              status={netHealth}
              label="READY"
              size="sm"
              className="justify-center"
            />
          </div>

          <div className="glass-panel p-2 rounded-lg border-white/10 text-center">
            <div className="flex items-center justify-center gap-1 text-[9px] font-mono text-zinc-400 mb-0.5">
              <Radio className="w-2.5 h-2.5 text-zinc-300" />
              <span>PING</span>
            </div>
            <div className="text-[10px] font-mono font-bold text-emerald-400">
              {pingDisplay}
            </div>
          </div>
        </div>

        {/* Toggleable Hardware / Neural Gauges */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between py-1 text-[10px] font-mono text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
        >
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3 text-zinc-400" />
            <span>{isConnected ? 'LIVE DESKTOP TELEMETRY' : 'NEURAL LINK TELEMETRY (SAMPLE)'}</span>
          </span>
          <motion.span animate={{ rotate: expanded ? 180 : 0 }} transition={{ duration: 0.2 }}>
            <ChevronDown className="w-3 h-3" />
          </motion.span>
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              className="overflow-hidden"
            >
              <div className="space-y-2 pb-1">
                {/* CPU Gauge */}
                <div className="space-y-0.5">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-zinc-300 flex items-center gap-1">
                      <Cpu className="w-3 h-3 text-zinc-400" />
                      {isConnected ? 'CPU Core Load' : 'Neural Core Synapse'}
                    </span>
                    <span className="text-white font-bold">{cpuPercent}%</span>
                  </div>
                  <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${cpuPercent}%` }}
                      transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                      className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                    />
                  </div>
                </div>

                {/* RAM Gauge */}
                <div className="space-y-0.5">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-zinc-300 flex items-center gap-1">
                      <HardDrive className="w-3 h-3 text-zinc-400" />
                      {isConnected ? 'Physical RAM' : 'Working Memory Pool'}
                    </span>
                    <span className="text-white font-bold">
                      {ramUsed}/{ramTotal}GB
                    </span>
                  </div>
                  <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${ramPercent}%` }}
                      transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                      className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                    />
                  </div>
                </div>

                {/* Disk Gauge */}
                <div className="space-y-0.5">
                  <div className="flex items-center justify-between text-[10px] font-mono">
                    <span className="text-zinc-300 flex items-center gap-1">
                      <HardDrive className="w-3 h-3 text-zinc-400" />
                      {isConnected ? 'Storage SSD' : 'Context Cache Space'}
                    </span>
                    <span className="text-white font-bold">
                      {diskUsed}/{diskTotal}GB
                    </span>
                  </div>
                  <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${diskPercent}%` }}
                      transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                      className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                    />
                  </div>
                </div>

                {!isConnected && (
                  <p className="text-[9px] font-mono text-zinc-500 pt-1 text-center">
                    Run <code className="text-zinc-400">python laptop_worker.py</code> on desktop to stream live hardware.
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </GlassCard>
  );
};
