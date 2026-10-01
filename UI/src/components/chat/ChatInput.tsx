import React, { useState } from 'react';
import { Mic, MicOff, Send, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAryaStore } from '../../store/useAryaStore';
import { useAudioLevel } from '../../hooks/useAudioLevel';
import { cn } from '../../lib/utils';
import { wsService } from '../../services/websocket';
import { audioPlayer } from '../../services/audioPlayer';

export const ChatInput: React.FC = () => {
  const [query, setQuery] = useState('');
  const [isFocused, setIsFocused] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const micEnabled = useAryaStore((s) => s.micEnabled);
  const toggleMic = useAryaStore((s) => s.toggleMic);
  const sendUserQuery = useAryaStore((s) => s.sendUserQuery);
  const voiceState = useAryaStore((s) => s.voiceState);

  const audioLevelsRef = useAudioLevel();

  const handleToggleMic = () => {
    audioPlayer.unlock();
    toggleMic();
  };

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    audioPlayer.unlock();
    setIsSubmitted(true);
    setTimeout(() => setIsSubmitted(false), 500);

    sendUserQuery(query.trim());
    setQuery('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const isBusy = voiceState === 'listening' || voiceState === 'thinking' || voiceState === 'speaking';
  const currentLevel = audioLevelsRef.current?.level || 0;

  return (
    <div className="w-full max-w-xl mx-auto relative z-20">
      <form
        onSubmit={handleSubmit}
        className={cn(
          'glass-panel p-2 pl-4 rounded-2xl flex items-center gap-3 transition-all duration-300 border-white/15 relative overflow-hidden',
          isFocused ? 'border-white/40 shadow-[0_0_30px_rgba(255,255,255,0.12)]' : '',
          micEnabled ? 'border-white/25 shadow-[0_0_25px_rgba(255,255,255,0.08)]' : 'border-white/10'
        )}
      >
        {/* Mic Toggle Button with expanding audio ring pulse */}
        <div className="relative flex items-center justify-center">
          {micEnabled && (
            <motion.div
              animate={{
                scale: [1, 1.2 + currentLevel * 0.8, 1],
                opacity: [0.6, 0.2, 0.6],
              }}
              transition={{ repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
              className="absolute inset-0 rounded-xl bg-white/30 border border-white/40 pointer-events-none"
            />
          )}

          <motion.button
            type="button"
            onClick={handleToggleMic}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className={cn(
              'p-2.5 rounded-xl transition-all flex items-center justify-center cursor-pointer shrink-0 relative z-10',
              micEnabled
                ? 'bg-white text-black shadow-[0_0_15px_rgba(255,255,255,0.4)]'
                : 'glass-button text-zinc-400 hover:text-white'
            )}
            title={micEnabled ? 'Mute Microphone' : 'Enable Voice Input'}
          >
            <AnimatePresence mode="wait">
              {micEnabled ? (
                <motion.div
                  key="mic-on"
                  initial={{ scale: 0, rotate: -90 }}
                  animate={{ scale: 1, rotate: 0 }}
                  exit={{ scale: 0, rotate: 90 }}
                  transition={{ duration: 0.15 }}
                >
                  <Mic className="w-4 h-4" />
                </motion.div>
              ) : (
                <motion.div
                  key="mic-off"
                  initial={{ scale: 0, rotate: 90 }}
                  animate={{ scale: 1, rotate: 0 }}
                  exit={{ scale: 0, rotate: -90 }}
                  transition={{ duration: 0.15 }}
                >
                  <MicOff className="w-4 h-4" />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        </div>

        {/* Text Input */}
        <input
          type="text"
          value={query}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            micEnabled
              ? 'Voice stream active... or type query here (Enter to send)'
              : 'Ask Arya anything... (Enter to send)'
          }
          disabled={isBusy && micEnabled}
          className="flex-1 bg-transparent text-sm text-white placeholder-zinc-400 focus:outline-none font-sans"
        />

        {/* Send Button with flying motion */}
        <motion.button
          type="submit"
          disabled={!query.trim() || (isBusy && micEnabled)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className={cn(
            'p-2.5 rounded-xl font-medium text-xs transition-all flex items-center justify-center cursor-pointer shrink-0 relative overflow-hidden',
            query.trim()
              ? 'bg-white text-black hover:bg-zinc-200 shadow-[0_0_15px_rgba(255,255,255,0.3)]'
              : 'glass-button opacity-40 cursor-not-allowed'
          )}
        >
          <motion.div
            animate={isSubmitted ? { y: [-20, 0], opacity: [0, 1] } : {}}
            transition={{ duration: 0.3 }}
          >
            <Send className="w-4 h-4" />
          </motion.div>
        </motion.button>
      </form>

      {/* Helper Voice State Indicator */}
      <div className="flex items-center justify-between text-[11px] font-mono text-zinc-400 px-3 mt-2">
        <span className="flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-zinc-400" />
          <span>Press Enter to dispatch intent</span>
        </span>
        <span>{micEnabled ? 'Full Duplex Audio ON' : 'Manual Text Query'}</span>
      </div>
    </div>
  );
};
