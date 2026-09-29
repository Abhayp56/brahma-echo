import React, { useRef, useState } from 'react';
import { motion, HTMLMotionProps } from 'framer-motion';
import { cn } from '../../lib/utils';

export interface GlassCardProps extends Omit<HTMLMotionProps<'div'>, 'title'> {
  children: React.ReactNode;
  title?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  hoverEffect?: boolean;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
}

export const GlassCard: React.FC<GlassCardProps> = ({
  children,
  title,
  action,
  icon,
  hoverEffect = true,
  className,
  headerClassName,
  contentClassName,
  ...props
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rotate, setRotate] = useState({ x: 0, y: 0 });
  const [sweepPos, setSweepPos] = useState({ x: 50, y: 50, opacity: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!hoverEffect || !cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // 3D Tilt calculation (max ~4 degrees)
    const centerX = rect.width / 2;
    const centerY = rect.height / 2;

    const rotX = ((y - centerY) / centerY) * -4;
    const rotY = ((x - centerX) / centerX) * 4;

    setRotate({ x: rotX, y: rotY });
    setSweepPos({ x, y, opacity: 1 });
  };

  const handleMouseLeave = () => {
    setRotate({ x: 0, y: 0 });
    setSweepPos((prev) => ({ ...prev, opacity: 0 }));
  };

  return (
    <motion.div
      ref={cardRef}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      animate={{
        rotateX: rotate.x,
        rotateY: rotate.y,
      }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      style={{ transformStyle: 'preserve-3d', perspective: 1000 }}
      className={cn(
        'glass-panel rounded-2xl p-5 flex flex-col relative overflow-hidden',
        hoverEffect && 'glass-panel-hover',
        className
      )}
      {...props}
    >
      {/* Light Sweep Highlight following cursor */}
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-500 z-0"
        style={{
          opacity: sweepPos.opacity,
          background: `radial-gradient(350px circle at ${sweepPos.x}px ${sweepPos.y}px, rgba(255, 255, 255, 0.08), transparent 70%)`,
        }}
      />

      {(title || action || icon) && (
        <div className={cn('flex items-center justify-between pb-3 mb-3 border-b border-white/10 relative z-10', headerClassName)}>
          <div className="flex items-center gap-2.5">
            {icon && <span className="text-zinc-300 text-sm">{icon}</span>}
            {typeof title === 'string' ? (
              <h3 className="text-sm font-semibold tracking-wider text-zinc-100 uppercase font-sans">
                {title}
              </h3>
            ) : (
              title
            )}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}

      <div className={cn('flex-1 relative z-10', contentClassName)}>{children}</div>
    </motion.div>
  );
};
