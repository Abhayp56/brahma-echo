import React from 'react';
import { Cpu, Layers, Sparkles, Power, Activity } from 'lucide-react';
import { motion } from 'framer-motion';
import { useAryaStore } from '../../store/useAryaStore';
import { GlassButton } from '../ui/GlassButton';
import { StatusDot } from '../ui/StatusDot';
import { topBarVariant } from '../../lib/motion';

export const TopBar: React.FC = () => {
  const desktopAgentState = useAryaStore((s) => s.desktopAgentState);
  const toggleDesktopAgent = useAryaStore((s) => s.toggleDesktopAgent);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const voiceState = useAryaStore((s) => s.voiceState);

  return (
    <motion.header
      variants={topBarVariant}
      initial="hidden"
      animate="visible"
      className="fixed top-0 left-0 right-0 z-40 px-6 py-4 flex items-center justify-between pointer-events-none"
    >
      {/* Left: Brand Identity */}
      <div className="flex items-center gap-3 pointer-events-auto">
        <div className="w-10 h-10 rounded-xl glass-panel border-white/20 flex items-center justify-center relative shadow-[0_0_20px_rgba(255,255,255,0.1)]">
          <Sparkles className="w-5 h-5 text-white animate-pulse" />
          <div className="absolute inset-0 rounded-xl bg-white/5 blur-sm -z-10" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-black tracking-widest text-white uppercase font-sans">
              ARYA
            </h1>
            <span className="px-1.5 py-0.5 rounded bg-white/10 text-[10px] font-mono text-zinc-300 border border-white/10 uppercase">
              AI SECRETARY v2.4
            </span>
          </div>
          <p className="text-[11px] text-zinc-400 font-mono flex items-center gap-1.5">
            <Activity className="w-3 h-3 text-emerald-400" />
            <span>State: </span>
            <span className="text-white capitalize font-semibold">{voiceState}</span>
          </p>
        </div>
      </div>

      {/* Right Controls: Desktop Agent Status, Cursor Toggle & Integrations */}
      <div className="flex items-center gap-3 pointer-events-auto">
        {/* Desktop Agent Indicator & Toggle */}
        <div className="glass-panel px-3.5 py-1.5 rounded-xl border-white/10 flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Cpu className="w-4 h-4 text-zinc-300" />
            <div className="flex flex-col">
              <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider">
                Desktop Agent
              </span>
              <StatusDot
                status={desktopAgentState.connected}
                label={desktopAgentState.connected ? 'ACTIVE' : 'OFFLINE'}
                size="sm"
              />
            </div>
          </div>

          <button
            onClick={() => toggleDesktopAgent()}
            title={desktopAgentState.connected ? 'Disconnect Agent' : 'Connect Agent'}
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
          >
            <Power className={`w-3.5 h-3.5 ${desktopAgentState.connected ? 'text-emerald-400' : 'text-rose-400'}`} />
          </button>
        </div>

        {/* Integrations Panel Trigger */}
        <GlassButton
          icon={<Layers className="w-4 h-4 text-zinc-200" />}
          onClick={() => setActiveModal('integrations')}
          variant="default"
          size="md"
        >
          Integrations
        </GlassButton>
      </div>
    </motion.header>
  );
};
