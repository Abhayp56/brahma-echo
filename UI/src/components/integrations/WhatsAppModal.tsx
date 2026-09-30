import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { QrCode, Loader2, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';
import { Modal } from '../ui/Modal';
import { GlassButton } from '../ui/GlassButton';
import { useAryaStore } from '../../store/useAryaStore';
import { whatsappService } from '../../services';
import { checkmarkVariant } from '../../lib/motion';

export const WhatsAppModal: React.FC = () => {
  const activeModal = useAryaStore((s) => s.activeModal);
  const setActiveModal = useAryaStore((s) => s.setActiveModal);
  const connectWhatsApp = useAryaStore((s) => s.connectWhatsApp);
  const disconnectWhatsApp = useAryaStore((s) => s.disconnectWhatsApp);
  const whatsappStatus = useAryaStore((s) => s.integrations.whatsapp);

  const [qrValue, setQrValue] = useState<string>('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanState, setScanState] = useState<'idle' | 'scanning' | 'success' | 'failed'>('idle');

  const isOpen = activeModal === 'whatsapp';

  const handleClose = () => {
    setActiveModal('integrations');
  };

  useEffect(() => {
    if (isOpen && !whatsappStatus.connected) {
      whatsappService.requestQRCode().then((res: { qrCodeValue: string }) => {
        setQrValue(res.qrCodeValue);
        setScanState('idle');
      });
    }
  }, [isOpen, whatsappStatus.connected]);

  const handleSimulateScan = async () => {
    setIsScanning(true);
    setScanState('scanning');

    const res = await connectWhatsApp();

    setIsScanning(false);
    if (res.success) {
      setScanState('success');
      setTimeout(() => {
        handleClose();
      }, 1600);
    } else {
      setScanState('failed');
    }
  };

  const handleDisconnect = async () => {
    await disconnectWhatsApp();
    handleClose();
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="WhatsApp Headless Bot Pairing"
      subtitle="Scan QR Code with WhatsApp (Linked Devices) to authorize Arya automated assistant"
      maxWidth="md"
    >
      <div className="space-y-5 flex flex-col items-center text-center">
        {whatsappStatus.connected ? (
          <div className="py-6 flex flex-col items-center gap-3">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
              {/* SVG Animated Path Checkmark */}
              <svg className="w-8 h-8 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <motion.path
                  d="M20 6L9 17l-5-5"
                  variants={checkmarkVariant}
                  initial="hidden"
                  animate="visible"
                />
              </svg>
            </div>
            <h3 className="text-base font-bold text-white">WhatsApp Headless Bot Connected</h3>
            <p className="text-xs text-zinc-400 font-mono">
              Linked Account: {whatsappStatus.details?.phoneNumber || '+1 (555) 019-2834'}
            </p>
          </div>
        ) : (
          <>
            {/* QR Code Canvas Frame with Scanning Line & Error Shake */}
            <motion.div
              animate={scanState === 'failed' ? { x: [-10, 10, -8, 8, -4, 4, 0] } : {}}
              transition={{ duration: 0.5 }}
              className="glass-panel p-5 rounded-2xl border-white/20 relative overflow-hidden shadow-[0_0_30px_rgba(255,255,255,0.1)]"
            >
              {qrValue ? (
                <div className="bg-white p-4 rounded-xl inline-block shadow-inner relative">
                  <QRCodeSVG value={qrValue} size={180} level="H" />
                  {/* Laser Scanning Line Animation */}
                  {scanState === 'scanning' && (
                    <motion.div
                      animate={{ y: [0, 170, 0] }}
                      transition={{ repeat: Infinity, duration: 1.8, ease: 'easeInOut' }}
                      className="absolute left-2 right-2 h-0.5 bg-emerald-400 shadow-[0_0_12px_#34d399]"
                    />
                  )}
                </div>
              ) : (
                <div className="w-48 h-48 flex items-center justify-center text-zinc-400">
                  <Loader2 className="w-8 h-8 animate-spin" />
                </div>
              )}

              {scanState === 'scanning' && (
                <div className="absolute inset-0 bg-black/80 backdrop-blur-sm rounded-2xl flex flex-col items-center justify-center gap-2 text-white">
                  <Loader2 className="w-8 h-8 text-white animate-spin" />
                  <span className="text-xs font-mono">Verifying Handshake...</span>
                </div>
              )}
            </motion.div>

            {/* Instruction / Scan State Feedback */}
            <div className="text-xs text-zinc-300 font-mono max-w-xs leading-relaxed">
              {scanState === 'failed' ? (
                <span className="text-rose-400 flex items-center justify-center gap-1">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>Scan timed out. Click simulate scan to retry.</span>
                </span>
              ) : (
                'Open WhatsApp > Menu / Settings > Linked Devices > Point camera at screen'
              )}
            </div>
          </>
        )}

        {/* Footer Actions */}
        <div className="w-full flex items-center justify-end gap-3 pt-3 border-t border-white/10">
          <GlassButton onClick={handleClose} variant="ghost">
            Close
          </GlassButton>

          {whatsappStatus.connected ? (
            <GlassButton onClick={handleDisconnect} variant="danger">
              Disconnect Bot
            </GlassButton>
          ) : (
            <GlassButton
              onClick={handleSimulateScan}
              variant="silver"
              disabled={isScanning}
              icon={
                isScanning ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <QrCode className="w-4 h-4" />
                )
              }
            >
              {isScanning ? 'Pairing Device...' : 'Simulate Phone Scan'}
            </GlassButton>
          )}
        </div>
      </div>
    </Modal>
  );
};
