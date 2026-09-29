import React from 'react';
import { cn } from '../../lib/utils';

interface StatusDotProps {
  status: boolean | 'connected' | 'optimal' | 'degraded' | 'offline' | 'error';
  pulse?: boolean;
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  pulse = true,
  size = 'md',
  label,
  className,
}) => {
  const isConnected = status === true || status === 'connected' || status === 'optimal';
  const isDegraded = status === 'degraded';

  const sizeClasses = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2.5 h-2.5',
    lg: 'w-3.5 h-3.5',
  };

  const bgClass = isConnected
    ? 'bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]'
    : isDegraded
    ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.6)]'
    : 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]';

  const pingClass = isConnected
    ? 'bg-emerald-400'
    : isDegraded
    ? 'bg-amber-400'
    : 'bg-rose-400';

  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      <span className="relative flex">
        {pulse && (
          <span
            className={cn(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
              pingClass
            )}
          />
        )}
        <span
          className={cn('relative inline-flex rounded-full transition-colors', sizeClasses[size], bgClass)}
        />
      </span>
      {label && <span className="text-xs text-zinc-300 font-mono tracking-wide">{label}</span>}
    </div>
  );
};
