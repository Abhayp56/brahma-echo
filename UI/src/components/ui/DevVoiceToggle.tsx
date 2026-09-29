import React, { useState, useEffect } from 'react';
import { useAryaStore } from '../../store/useAryaStore';
import { VoiceState } from '../../types/arya';

interface DevVoiceToggleProps {
  onOverrideChange?: (state: VoiceState | 'auto') => void;
  activeOverride?: VoiceState | 'auto';
}

export const DevVoiceToggle: React.FC<DevVoiceToggleProps> = ({
  onOverrideChange,
  activeOverride = 'auto',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const setStoreVoiceState = useAryaStore((s) => s.setVoiceState);

  // Toggle on pressing key 'D'
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if typing in an input element
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (e.key === 'd' || e.key === 'D') {
        setIsOpen((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleSelectState = (state: VoiceState | 'auto') => {
    if (onOverrideChange) {
      onOverrideChange(state);
    }
    if (state !== 'auto') {
      setStoreVoiceState(state);
    }
  };

  return (
    <>
      {/* Tiny plain HTML "?" dev toggle button in bottom right */}
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="fixed bottom-4 right-4 z-50 w-7 h-7 rounded-full bg-black/60 border border-white/20 text-zinc-400 hover:text-white hover:border-white/50 text-xs font-mono flex items-center justify-center transition-all cursor-pointer shadow-lg backdrop-blur-md"
        title="Toggle Dev Voice Controls (Press 'D')"
      >
        ?
      </button>

      {/* Dev Overlay Panel */}
      {isOpen && (
        <div className="fixed bottom-14 right-4 z-50 bg-black/90 border border-white/20 rounded-xl p-3 shadow-2xl backdrop-blur-md text-xs font-mono w-64 text-white">
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10 text-zinc-400">
            <span>Dev Voice Simulator</span>
            <span className="text-[10px] bg-white/10 px-1.5 py-0.5 rounded text-zinc-300">
              Press 'D'
            </span>
          </div>

          <div className="text-[11px] text-zinc-400 mb-2">
            Force VoiceState:
          </div>

          <div className="grid grid-cols-2 gap-1.5">
            {(['auto', 'idle', 'listening', 'thinking', 'speaking'] as const).map(
              (st) => {
                const isActive = activeOverride === st;
                return (
                  <button
                    key={st}
                    onClick={() => handleSelectState(st)}
                    className={`px-2.5 py-1.5 rounded text-left capitalize transition-all cursor-pointer border ${
                      isActive
                        ? 'bg-white text-black font-semibold border-white'
                        : 'bg-white/5 text-zinc-300 border-white/10 hover:bg-white/15 hover:text-white'
                    }`}
                  >
                    {st}
                  </button>
                );
              }
            )}
          </div>
        </div>
      )}
    </>
  );
};
