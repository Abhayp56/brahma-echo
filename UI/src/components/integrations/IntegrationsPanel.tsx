import React, { useEffect } from 'react';
import { Send, MessageSquare, Smartphone, ChevronRight } from 'lucide-react';
import { Modal } from '../ui/Modal';
import { GlassButton } from '../ui/GlassButton';
import { StatusDot } from '../ui/StatusDot';
import { useAryaStore } from '../../store/useAryaStore';

export const IntegrationsPanel: React.FC = () => {
  const activeModal = useAryaStore((s) => s.activeModal);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const integrations = useAryaStore((s) => s.integrations);
  const loadIntegrationStatuses = useAryaStore((s) => s.loadIntegrationStatuses);

  const isOpen = activeModal === 'integrations';

  useEffect(() => {
    if (isOpen) {
      loadIntegrationStatuses();
    }
  }, [isOpen, loadIntegrationStatuses]);

  const handleClose = () => {
    setActiveModal('none');
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Channels & External Integrations"
      subtitle="Connect Arya to your mobile messaging platforms and companion app"
      maxWidth="xl"
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Telegram Card */}
        <div className="glass-panel p-4 rounded-2xl border-white/10 flex flex-col justify-between hover:border-white/20 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-sky-500/20 border border-sky-500/30 flex items-center justify-center text-sky-400">
                <Send className="w-5 h-5" />
              </div>
              <StatusDot status={integrations.telegram.connected} />
            </div>
            <h4 className="text-sm font-bold text-white mb-1">Telegram Bot</h4>
            <p className="text-xs text-zinc-400 leading-relaxed mb-4">
              Receive voice note transcripts & dispatch remote commands via custom Telegram bot.
            </p>
          </div>

          <div>
            <div className="text-[11px] font-mono text-zinc-400 mb-3 truncate">
              Status: {integrations.telegram.statusText || 'Disconnected'}
            </div>
            <GlassButton
              onClick={() => setActiveModal('telegram')}
              variant="default"
              size="sm"
              className="w-full justify-between"
            >
              <span>{integrations.telegram.connected ? 'Configure Bot' : 'Connect Bot'}</span>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />
            </GlassButton>
          </div>
        </div>

        {/* WhatsApp Card */}
        <div className="glass-panel p-4 rounded-2xl border-white/10 flex flex-col justify-between hover:border-white/20 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <MessageSquare className="w-5 h-5" />
              </div>
              <StatusDot status={integrations.whatsapp.connected} />
            </div>
            <h4 className="text-sm font-bold text-white mb-1">WhatsApp Bot</h4>
            <p className="text-xs text-zinc-400 leading-relaxed mb-4">
              Headless Web bot for automated message parsing, notifications, and client queries.
            </p>
          </div>

          <div>
            <div className="text-[11px] font-mono text-zinc-400 mb-3 truncate">
              Status: {integrations.whatsapp.statusText || 'Disconnected'}
            </div>
            <GlassButton
              onClick={() => setActiveModal('whatsapp')}
              variant="default"
              size="sm"
              className="w-full justify-between"
            >
              <span>{integrations.whatsapp.connected ? 'Manage Link' : 'Scan QR Code'}</span>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />
            </GlassButton>
          </div>
        </div>

        {/* Android Companion App Card */}
        <div className="glass-panel p-4 rounded-2xl border-white/10 flex flex-col justify-between hover:border-white/20 transition-all">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-purple-500/20 border border-purple-500/30 flex items-center justify-center text-purple-400">
                <Smartphone className="w-5 h-5" />
              </div>
              <StatusDot status={integrations.android.connected} />
            </div>
            <h4 className="text-sm font-bold text-white mb-1">Android Companion</h4>
            <p className="text-xs text-zinc-400 leading-relaxed mb-4">
              Full-duplex phone-call style real-time voice conversations with ultra-low latency.
            </p>
          </div>

          <div>
            <div className="text-[11px] font-mono text-zinc-400 mb-3 truncate">
              Status: {integrations.android.statusText || 'Disconnected'}
            </div>
            <GlassButton
              onClick={() => setActiveModal('android')}
              variant="default"
              size="sm"
              className="w-full justify-between"
            >
              <span>{integrations.android.connected ? 'Device Settings' : 'Pair Phone'}</span>
              <ChevronRight className="w-3.5 h-3.5 text-zinc-400" />
            </GlassButton>
          </div>
        </div>
      </div>
    </Modal>
  );
};
