import React, { useState } from 'react';
import { Send, Key, User, Hash, Loader2 } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';
import { TelegramConfig } from '../../types/arya';

export const TelegramModal: React.FC = () => {
  const activeModal = useAryaStore((s) => s.activeModal);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const connectTelegram = useAryaStore((s) => s.connectTelegram);
  const disconnectTelegram = useAryaStore((s) => s.disconnectTelegram);
  const telegramStatus = useAryaStore((s) => s.integrations.telegram);

  const [config, setConfig] = useState<TelegramConfig>({
    botToken: '6892341029:AAHk8-X992zKjL104mPqWvE_Mock',
    botName: 'AryaAssistantBot',
    chatId: '984021984',
  });
  const [loading, setLoading] = useState(false);

  const isOpen = activeModal === 'telegram';

  const handleClose = () => {
    setActiveModal('integrations');
  };

  const handleConnect = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const success = await connectTelegram(config);
    setLoading(false);
    if (success) {
      handleClose();
    }
  };

  const handleDisconnect = async () => {
    setLoading(true);
    await disconnectTelegram();
    setLoading(false);
    handleClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Telegram Bot Integration"
      subtitle="Connect Arya to your Telegram Bot for remote voice notes & command relay"
      maxWidth="md"
    >
      <form onSubmit={handleConnect} className="space-y-4">
        {/* Bot Token Field */}
        <div>
          <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
            <Key className="w-3.5 h-3.5 text-zinc-400" />
            <span>Bot Token</span>
          </label>
          <input
            type="password"
            value={config.botToken}
            onChange={(e) => setConfig({ ...config, botToken: e.target.value })}
            placeholder="123456789:ABCdefGHIjklmNOPqrstUVWxyz"
            className="glass-input w-full px-3.5 py-2 rounded-xl text-xs font-mono placeholder-zinc-400"
          />
        </div>

        {/* Bot Name Field */}
        <div>
          <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 text-zinc-400" />
            <span>Bot Name / Username</span>
          </label>
          <input
            type="text"
            value={config.botName}
            onChange={(e) => setConfig({ ...config, botName: e.target.value })}
            placeholder="@AryaAssistantBot"
            className="glass-input w-full px-3.5 py-2 rounded-xl text-xs placeholder-zinc-400 font-sans"
          />
        </div>

        {/* Chat ID Field */}
        <div>
          <label className="block text-xs font-mono text-zinc-300 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
            <Hash className="w-3.5 h-3.5 text-zinc-400" />
            <span>User / Channel Chat ID</span>
          </label>
          <input
            type="text"
            value={config.chatId}
            onChange={(e) => setConfig({ ...config, chatId: e.target.value })}
            placeholder="984021984"
            className="glass-input w-full px-3.5 py-2 rounded-xl text-xs font-mono placeholder-zinc-400"
          />
        </div>

        {/* Status Info */}
        <div className="glass-panel p-3 rounded-xl border-white/10 text-xs flex items-center justify-between">
          <span className="text-zinc-400 font-mono">Current Status:</span>
          <span className={telegramStatus.connected ? 'text-emerald-400 font-bold' : 'text-zinc-400'}>
            {telegramStatus.statusText}
          </span>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-white/10">
          <GlassButton type="button" onClick={handleClose} variant="ghost">
            Cancel
          </GlassButton>
          {telegramStatus.connected ? (
            <GlassButton
              type="button"
              onClick={handleDisconnect}
              variant="danger"
              disabled={loading}
            >
              Disconnect Bot
            </GlassButton>
          ) : (
            <GlassButton
              type="submit"
              variant="silver"
              disabled={loading}
              icon={loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            >
              {loading ? 'Validating Token...' : 'Connect Telegram'}
            </GlassButton>
          )}
        </div>
      </form>
    </Modal>
  );
};
