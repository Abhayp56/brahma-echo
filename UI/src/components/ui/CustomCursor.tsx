// @ts-nocheck
import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useAryaStore } from '../../store/useAryaStore';

export const CustomCursor: React.FC = () => {
  const customCursorEnabled = useAryaStore((s) => s.customCursorEnabled);

  const [mousePos, setMousePos] = useState({ x: -100, y: -100 });
  const [isHovered, setIsHovered] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    if (!customCursorEnabled) return;

    const handleMouseMove = (e: MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY });
      if (!isVisible) setIsVisible(true);

      const target = e.target as HTMLElement;
      if (
        target &&
        (target.tagName === 'BUTTON' ||
          target.tagName === 'A' ||
          target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.closest('button') ||
          target.closest('.glass-panel-hover') ||
          target.getAttribute('role') === 'button')
      ) {
        setIsHovered(true);
      } else {
        setIsHovered(false);
      }
    };

    const handleMouseLeave = () => setIsVisible(false);
    const handleMouseEnter = () => setIsVisible(true);

    window.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseleave', handleMouseLeave);
    document.addEventListener('mouseenter', handleMouseEnter);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseleave', handleMouseLeave);
      document.removeEventListener('mouseenter', handleMouseEnter);
    };
  }, [customCursorEnabled, isVisible]);

  if (!customCursorEnabled || !isVisible) return null;

  return (
    <div className="pointer-events-none fixed inset-0 z-[9999] overflow-hidden">
      {/* Inner Glowing Center Dot */}
      <motion.div
        className="fixed top-0 left-0 w-2.5 h-2.5 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.8)] pointer-events-none"
        animate={{
          x: mousePos.x - 5,
          y: mousePos.y - 5,
          scale: isHovered ? 1.4 : 1.0,
        }}
        transition={{ type: 'spring', stiffness: 1200, damping: 50, mass: 0.1 }}
      />

      {/* Lagging Ring Outer Orbit */}
      <motion.div
        className="fixed top-0 left-0 w-8 h-8 rounded-full border border-white/40 pointer-events-none"
        animate={{
          x: mousePos.x - 16,
          y: mousePos.y - 16,
          scale: isHovered ? 1.7 : 1.0,
          borderColor: isHovered ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.3)',
        }}
        transition={{ type: 'spring', stiffness: 350, damping: 25 }}
      />
    </div>
  );
};
