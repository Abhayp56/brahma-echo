import React from 'react';
import { Box } from 'lucide-react';
import { GlassButton } from '../ui/GlassButton';
import { wsService } from '../../services/websocket';
import { useAryaStore } from '../../store/useAryaStore';

export const HolographicBoardButton: React.FC = () => {
  const addToast = useAryaStore((s) => s.addToast);

  const handleClick = () => {
    wsService.sendAction('holographic_board');
    addToast({
      title: 'Holographic Board Projected',
      description: 'Projecting Holographic Spatial Task Board onto active workspace...',
      type: 'success',
    });
  };

  return (
    <GlassButton
      icon={<Box className="w-4 h-4 text-white" />}
      onClick={handleClick}
      variant="default"
      size="md"
    >
      Holographic Board
    </GlassButton>
  );
};
