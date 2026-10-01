import React, { useRef, useEffect } from 'react';
import { MessageSquare, Trash2, User, Sparkles, Terminal } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';

export const Transcript: React.FC = () => {
  const transcript = useAryaStore((s) => s.transcript);
  const clearTranscript = useAryaStore((s) => s.clearTranscript);
  const voiceState = useAryaStore((s) => s.voiceState);

  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript, voiceState]);

  return (
    <GlassCard
      title="Live Conversation"
      icon={<MessageSquare className="w-4 h-4 text-white" />}
      action={
        transcript.length > 0 ? (
          <GlassButton
            onClick={clearTranscript}
            variant="ghost"
            size="sm"
            icon={<Trash2 className="w-3.5 h-3.5 text-zinc-400 hover:text-rose-400 transition-colors" />}
            title="Clear transcript"
          >
            Clear
          </GlassButton>
        ) : undefined
      }
      className="w-full h-full flex flex-col min-h-0"
      contentClassName="flex-1 flex flex-col min-h-0"
    >
      <div className="flex-1 flex flex-col min-h-0">
        <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-3 pr-1 min-h-0">
          {transcript.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-zinc-500 font-mono text-xs">
              <div className="w-10 h-10 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-3 text-zinc-400">
                <MessageSquare className="w-5 h-5" />
              </div>
              <p className="font-semibold text-zinc-300 mb-1">Live Audio & Intent Stream</p>
              <p className="text-[11px] text-zinc-500 max-w-[220px]">
                Speak into the microphone or type below to converse with Arya.
              </p>
            </div>
          ) : (
            <AnimatePresence initial={false}>
              {transcript.map((msg) => {
                const isUser = msg.sender === 'user';
                const isArya = msg.sender === 'arya';
                const isSystem = msg.sender === 'system';

                if (isSystem) {
                  return (
                    <motion.div
                      key={msg.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.3 }}
                      className="glass-panel px-3 py-1.5 rounded-lg border-white/5 text-[10px] font-mono text-zinc-400 flex items-center justify-between"
                    >
                      <span className="flex items-center gap-1.5">
                        <Terminal className="w-3 h-3 text-zinc-400" />
                        <span>{msg.text}</span>
                      </span>
                      <span>{msg.timestamp}</span>
                    </motion.div>
                  );
                }

                return (
                  <motion.div
                    key={msg.id}
                    initial={{ opacity: 0, y: 12, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    transition={{ type: 'spring', stiffness: 350, damping: 25 }}
                    className={`flex flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}
                  >
                    <div className="flex items-center gap-1.5 text-[10px] font-mono text-zinc-400">
                      {isUser ? (
                        <>
                          <span>{msg.timestamp}</span>
                          <span className="text-white font-semibold">YOU</span>
                          <User className="w-3 h-3 text-zinc-300" />
                        </>
                      ) : (
                        <>
                          <Sparkles className="w-3 h-3 text-white" />
                          <span className="text-white font-semibold">ARYA</span>
                          <span>{msg.timestamp}</span>
                        </>
                      )}
                    </div>

                    <div
                      className={`max-w-[88%] p-3 rounded-2xl text-xs leading-relaxed ${
                        isUser
                          ? 'bg-white/10 text-white border border-white/20 rounded-tr-none shadow-[0_0_15px_rgba(255,255,255,0.05)]'
                          : 'glass-panel text-zinc-200 border-white/10 rounded-tl-none'
                      }`}
                    >
                      {msg.text}
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          )}

          {/* Typing Indicator while Arya is thinking */}
          {voiceState === 'thinking' && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2 glass-panel p-3 rounded-2xl border-white/10 w-24 text-zinc-400"
            >
              <Sparkles className="w-3.5 h-3.5 text-white animate-spin-slow" />
              <div className="flex items-center gap-1">
                <motion.span
                  animate={{ y: [0, -4, 0] }}
                  transition={{ repeat: Infinity, duration: 0.6, delay: 0 }}
                  className="w-1.5 h-1.5 rounded-full bg-white inline-block"
                />
                <motion.span
                  animate={{ y: [0, -4, 0] }}
                  transition={{ repeat: Infinity, duration: 0.6, delay: 0.15 }}
                  className="w-1.5 h-1.5 rounded-full bg-white inline-block"
                />
                <motion.span
                  animate={{ y: [0, -4, 0] }}
                  transition={{ repeat: Infinity, duration: 0.6, delay: 0.3 }}
                  className="w-1.5 h-1.5 rounded-full bg-white inline-block"
                />
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </GlassCard>
  );
};
