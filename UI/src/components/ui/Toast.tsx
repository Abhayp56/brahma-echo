import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, AlertCircle, Info, AlertTriangle, X } from 'lucide-react';
import { useAryaStore } from '../../store/useAryaStore';
import { ToastNotification } from '../../types/arya';

const ToastItem: React.FC<{ toast: ToastNotification; onRemove: (id: string) => void }> = ({
  toast,
  onRemove,
}) => {
  const icons = {
    success: <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />,
    error: <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />,
    warning: <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />,
    info: <Info className="w-4 h-4 text-sky-400 shrink-0" />,
  };

  const borderColors = {
    success: 'border-emerald-500/30',
    error: 'border-rose-500/30',
    warning: 'border-amber-500/30',
    info: 'border-white/20',
  };

  const durationSec = (toast.duration || 4000) / 1000;

  return (
    <motion.div
      layout
      drag="x"
      dragConstraints={{ left: 0, right: 120 }}
      onDragEnd={(_, info) => {
        if (info.offset.x > 80) {
          onRemove(toast.id);
        }
      }}
      initial={{ opacity: 0, x: 80, scale: 0.9 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 80, scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 380, damping: 24 }}
      className={`glass-panel p-4 rounded-xl border ${borderColors[toast.type]} shadow-xl flex flex-col gap-2 max-w-sm w-full relative overflow-hidden cursor-grab active:cursor-grabbing`}
    >
      <div className="flex items-start gap-3">
        {icons[toast.type]}
        <div className="flex-1 min-w-0 pr-2">
          <h4 className="text-xs font-bold text-white tracking-wide">{toast.title}</h4>
          {toast.description && (
            <p className="text-xs text-zinc-300 mt-0.5 leading-relaxed">{toast.description}</p>
          )}
        </div>
        <button
          onClick={() => onRemove(toast.id)}
          className="text-zinc-400 hover:text-white p-1 rounded hover:bg-white/10 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Auto-Dismiss Progress Bar */}
      <div className="w-full bg-white/10 h-0.5 rounded-full overflow-hidden mt-1">
        <motion.div
          initial={{ width: '100%' }}
          animate={{ width: '0%' }}
          transition={{ duration: durationSec, ease: 'linear' }}
          className="h-full bg-white/60"
        />
      </div>
    </motion.div>
  );
};

export const ToastContainer: React.FC = () => {
  const toasts = useAryaStore((s) => s.toasts);
  const removeToast = useAryaStore((s) => s.removeToast);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2.5 pointer-events-auto">
      <AnimatePresence>
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={removeToast} />
        ))}
      </AnimatePresence>
    </div>
  );
};
