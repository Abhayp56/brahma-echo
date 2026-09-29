import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Smartphone, Loader2, ShieldCheck } from 'lucide-react';
import { motion } from 'framer-motion';
import { Modal } from '../ui/Modal';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';
import { androidService } from '../../services';
import { checkmarkVariant } from '../../lib/motion';

export const AndroidModal: React.FC = () => {
  const activeModal = useAryaStore((s) => s.activeModal);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const connectAndroid = useAryaStore((s) => s.connectAndroid);
  const disconnectAndroid = useAryaStore((s) => s.disconnectAndroid);
  const androidStatus = useAryaStore((s) => s.integrations.android);

  const [qrValue, setQrValue] = useState<string>('');
  const [pairingCode, setPairingCode] = useState<string>('');
  const [isPairing, setIsPairing] = useState(false);

  const isOpen = activeModal === 'android';

  const handleClose = () => {
    setActiveModal('integrations');
  };

  useEffect(() => {
    if (isOpen && !androidStatus.connected) {
      androidService.requestPairingData().then((res) => {
        setQrValue(res.qrCodeValue);
        setPairingCode(res.pairingCode);
      });
    }
  }, [isOpen, androidStatus.connected]);

  const handleSimulatePairing = async () => {
    setIsPairing(true);
    const res = await connectAndroid();
    setIsPairing(false);
    if (res.success) {
      setTimeout(() => {
        handleClose();
      }, 1600);
    }
  };

  const handleDisconnect = async () => {
    await disconnectAndroid();
    handleClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Android Companion App Link"
      subtitle="Pair your Android smartphone for phone-call style real-time voice conversations"
      maxWidth="md"
    >
      <div className="space-y-5 flex flex-col items-center text-center">
        {androidStatus.connected ? (
          <div className="py-6 flex flex-col items-center gap-3">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              <svg className="w-8 h-8 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <motion.path
                  d="M20 6L9 17l-5-5"
                  variants={checkmarkVariant}
                  initial="hidden"
                  animate="visible"
                />
              </svg>
            </div>
            <h3 className="text-base font-bold text-white">Android Device Linked</h3>
            <div className="glass-panel p-3 rounded-xl border-white/10 text-xs font-mono text-zinc-300 space-y-1">
              <div>Device: {androidStatus.details?.deviceName || 'Pixel 8 Pro'}</div>
              <div>Audio Pipeline: Full-Duplex Low Latency (14ms)</div>
              <div>Battery Status: {androidStatus.details?.battery || '88%'}</div>
            </div>
          </div>
        ) : (
          <>
            {/* QR Code and Pairing Code display */}
            <div className="flex flex-col sm:flex-row items-center gap-6">
              <div className="glass-panel p-4 rounded-2xl border-white/20 relative overflow-hidden shadow-[0_0_30px_rgba(255,255,255,0.1)]">
                {qrValue ? (
                  <div className="bg-white p-3 rounded-xl inline-block relative">
                    <QRCodeSVG value={qrValue} size={150} level="M" />
                    {isPairing && (
                      <motion.div
                        animate={{ y: [0, 140, 0] }}
                        transition={{ repeat: Infinity, duration: 1.6, ease: 'easeInOut' }}
                        className="absolute left-2 right-2 h-0.5 bg-emerald-400 shadow-[0_0_12px_#34d399]"
                      />
                    )}
                  </div>
                ) : (
                  <div className="w-40 h-40 flex items-center justify-center text-zinc-400">
                    <Loader2 className="w-8 h-8 animate-spin" />
                  </div>
                )}
              </div>

              <div className="flex flex-col items-center sm:items-start text-center sm:text-left space-y-2">
                <span className="text-xs font-mono text-zinc-400 uppercase">
                  Or enter 6-digit PIN in app:
                </span>
                <div className="glass-panel px-4 py-2 rounded-xl border-white/20 text-xl font-mono tracking-widest text-white font-bold">
                  {pairingCode || '482-910'}
                </div>
                <p className="text-[11px] text-zinc-400 max-w-xs leading-relaxed">
                  Open the Arya Companion app on Android, tap "Pair Desktop Host", and scan or type this code.
                </p>
              </div>
            </div>

            <div className="glass-panel p-3 rounded-xl border-white/10 text-xs text-zinc-300 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
              <span>AES-256 End-to-End Encrypted Audio Stream</span>
            </div>
          </>
        )}

        {/* Footer Actions */}
        <div className="w-full flex items-center justify-end gap-3 pt-3 border-t border-white/10">
          <GlassButton onClick={handleClose} variant="ghost">
            Close
          </GlassButton>

          {androidStatus.connected ? (
            <GlassButton onClick={handleDisconnect} variant="danger">
              Unlink Companion
            </GlassButton>
          ) : (
            <GlassButton
              onClick={handleSimulatePairing}
              variant="silver"
              disabled={isPairing}
              icon={
                isPairing ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Smartphone className="w-4 h-4" />
                )
              }
            >
              {isPairing ? 'Establishing Stream...' : 'Simulate Companion Pair'}
            </GlassButton>
          )}
        </div>
      </div>
    </Modal>
  );
};
