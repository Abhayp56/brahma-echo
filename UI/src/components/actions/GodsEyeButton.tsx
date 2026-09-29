import React from 'react';
import { Eye } from 'lucide-react';
import { GlassButton } from '../ui/GlassButton';
import { wsService } from '../../services/websocket';
import { useAryaStore } from '../../store/useAryaStore';

export const GodsEyeButton: React.FC = () => {
  const addToast = useAryaStore((s) => s.addToast);

  const handleClick = () => {
    wsService.sendAction('gods_eye');
    addToast({
      title: "God's Eye Activated",
      description: "Opening God's Eye 360° Process & Visual Inspector on your desktop...",
      type: 'success',
    });
  };

  return (
    <GlassButton
      icon={<Eye className="w-4 h-4 text-white" />}
      onClick={handleClick}
      variant="default"
      size="md"
    >
      God's Eye
    </GlassButton>
  );
};
