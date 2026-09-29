import React, { useRef, useState } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { cn } from '../../lib/utils';
import { springConfig } from '../../lib/motion';

interface GlassButtonProps extends HTMLMotionProps<'button'> {
  icon?: React.ReactNode;
  children: React.ReactNode;
  variant?: 'default' | 'silver' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  active?: boolean;
}

export const GlassButton: React.FC<GlassButtonProps> = ({
  icon,
  children,
  variant = 'default',
  size = 'md',
  active = false,
  className,
  ...props
}) => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [spotlightPos, setSpotlightPos] = useState({ x: 50, y: 50, opacity: 0 });
  const [magneticOffset, setMagneticOffset] = useState({ x: 0, y: 0 });

  const sizeClasses = {
    sm: 'px-3 py-1.5 text-xs rounded-lg gap-1.5',
    md: 'px-4 py-2 text-xs font-medium rounded-xl gap-2',
    lg: 'px-5 py-2.5 text-sm font-semibold rounded-xl gap-2.5',
  };

  const variantClasses = {
    default: 'glass-button border-white/10 hover:border-white/25 text-zinc-200 hover:text-white',
    silver: 'bg-white/10 hover:bg-white/20 border-white/30 text-white shadow-[0_0_15px_rgba(255,255,255,0.15)]',
    danger: 'bg-rose-950/40 hover:bg-rose-900/60 border-rose-500/30 text-rose-300 hover:text-rose-100',
    ghost: 'bg-transparent border-transparent hover:bg-white/5 text-zinc-400 hover:text-white',
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    setSpotlightPos({ x, y, opacity: 1 });

    // Magnetic pull calculation (max 4px movement)
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const magX = (x - centerX) * 0.15;
    const magY = (y - centerY) * 0.15;

    setMagneticOffset({ x: magX, y: magY });
  };

  const handleMouseLeave = () => {
    setSpotlightPos((prev) => ({ ...prev, opacity: 0 }));
    setMagneticOffset({ x: 0, y: 0 });
  };

  return (
    <motion.button
      ref={buttonRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      animate={{ x: magneticOffset.x, y: magneticOffset.y }}
      whileHover={{ scale: 1.03, y: -2 }}
      whileTap={{ scale: 0.95 }}
      transition={springConfig}
      className={cn(
        'relative inline-flex items-center justify-center font-sans tracking-wide cursor-pointer transition-all disabled:opacity-50 disabled:cursor-not-allowed select-none overflow-hidden',
        sizeClasses[size],
        variantClasses[variant],
        active && 'bg-white/20 border-white/40 text-white shadow-[0_0_20px_rgba(255,255,255,0.2)]',
        className
      )}
      {...props}
    >
      {/* Radial Spotlight Overlay following cursor */}
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-300"
        style={{
          opacity: spotlightPos.opacity,
          background: `radial-gradient(120px circle at ${spotlightPos.x}px ${spotlightPos.y}px, rgba(255, 255, 255, 0.18), transparent 80%)`,
        }}
      />

      {icon && (
        <motion.span
          whileHover={{ scale: 1.15, rotate: 8 }}
          transition={{ type: 'spring', stiffness: 400 }}
          className="shrink-0 text-current relative z-10"
        >
          {icon}
        </motion.span>
      )}

      <span className="relative z-10">{children}</span>
    </motion.button>
  );
};
