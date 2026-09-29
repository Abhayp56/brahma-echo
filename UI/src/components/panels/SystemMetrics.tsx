import React, { useEffect, useState } from 'react';
import { Cpu, HardDrive, Zap, Network, Radio, AlertTriangle, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { StatusDot } from '../ui/StatusDot';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';
import { metricsService } from '../../services';

/**
 * SystemMetrics — Collapsible panel.
 * Stage 3: Always shows status dots row. Gauges toggle open/closed.
 */
export const SystemMetrics: React.FC = () => {
  const desktopAgentState = useAryaStore((s) => s.desktopAgentState);
  const toggleDesktopAgent = useAryaStore((s) => s.toggleDesktopAgent);
  const metrics = useAryaStore((s) => s.metrics);
  const setMetrics = useAryaStore((s) => s.setMetrics);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const unsubscribe = metricsService.subscribeMetrics((data) => {
      setMetrics(data);
    });
    return () => unsubscribe();
  }, [setMetrics]);

  return (
    <GlassCard
      title="System Metrics"
      icon={<Cpu className="w-4 h-4 text-white" />}
      action={
        <StatusDot
          status={desktopAgentState.connected ? 'optimal' : 'offline'}
          label={desktopAgentState.connected ? 'LINKED' : 'UNLINKED'}
          size="sm"
        />
      }
      className="w-full flex-shrink-0"
    >
      <div className="space-y-2">
        {/* Status row — always visible */}
        <div className="grid grid-cols-3 gap-1.5">
          <div className="glass-panel p-2 rounded-lg border-white/10 text-center relative overflow-hidden">
            {metrics?.neuralLinkHealth === 'degraded' && (
              <div className="absolute inset-0 bg-amber-500/10 animate-pulse pointer-events-none" />
            )}
            <div className="flex items-center justify-center gap-1 text-[9px] font-mono text-zinc-400 mb-0.5">
              <Zap className="w-2.5 h-2.5 text-zinc-300" />
              <span>LINK</span>
            </div>
            <StatusDot
              status={metrics?.neuralLinkHealth || 'optimal'}
              label={metrics?.neuralLinkHealth?.toUpperCase() || 'OK'}
              size="sm"
              className="justify-center"
            />
          </div>
          <div className="glass-panel p-2 rounded-lg border-white/10 text-center relative overflow-hidden">
            {metrics?.networkHealth === 'degraded' && (
              <div className="absolute inset-0 bg-amber-500/10 animate-pulse pointer-events-none" />
            )}
            <div className="flex items-center justify-center gap-1 text-[9px] font-mono text-zinc-400 mb-0.5">
              <Network className="w-2.5 h-2.5 text-zinc-300" />
              <span>NET</span>
            </div>
            <StatusDot
              status={metrics?.networkHealth || 'optimal'}
              label={metrics?.networkHealth?.toUpperCase() || 'OK'}
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
              {metrics?.latencyMs || 14}ms
            </div>
          </div>
        </div>

        {/* Toggle gauges */}
        {desktopAgentState.connected && (
          <>
            <button
              onClick={() => setExpanded(!expanded)}
              className="w-full flex items-center justify-between py-1 text-[10px] font-mono text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
            >
              <span>HARDWARE GAUGES</span>
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
                    {/* CPU */}
                    <div className="space-y-0.5">
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="text-zinc-300 flex items-center gap-1">
                          <Cpu className="w-3 h-3 text-zinc-400" />CPU
                        </span>
                        <span className="text-white font-bold">{metrics?.cpuUsage || 24}%</span>
                      </div>
                      <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${metrics?.cpuUsage || 24}%` }}
                          transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                          className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                        />
                      </div>
                    </div>
                    {/* RAM */}
                    <div className="space-y-0.5">
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="text-zinc-300 flex items-center gap-1">
                          <HardDrive className="w-3 h-3 text-zinc-400" />RAM
                        </span>
                        <span className="text-white font-bold">
                          {metrics?.ramUsedGB || 15.3}/{metrics?.ramTotalGB || 32}GB
                        </span>
                      </div>
                      <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${metrics?.ramUsage || 48}%` }}
                          transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                          className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                        />
                      </div>
                    </div>
                    {/* Disk */}
                    <div className="space-y-0.5">
                      <div className="flex items-center justify-between text-[10px] font-mono">
                        <span className="text-zinc-300 flex items-center gap-1">
                          <HardDrive className="w-3 h-3 text-zinc-400" />SSD
                        </span>
                        <span className="text-white font-bold">
                          {metrics?.diskUsedGB || 620}/{metrics?.diskTotalGB || 1000}GB
                        </span>
                      </div>
                      <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden border border-white/10">
                        <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${metrics?.diskUsage || 62}%` }}
                          transition={{ type: 'spring', stiffness: 100, damping: 15 }}
                          className="bg-gradient-to-r from-zinc-400 to-white h-full rounded-full"
                        />
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </>
        )}

        {!desktopAgentState.connected && (
          <div className="glass-panel p-4 rounded-xl border-white/10 text-center flex flex-col items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <p className="text-[10px] text-zinc-400 font-mono">Agent offline</p>
            <GlassButton onClick={() => toggleDesktopAgent()} variant="silver" size="sm">
              Connect
            </GlassButton>
          </div>
        )}
      </div>
    </GlassCard>
  );
};
