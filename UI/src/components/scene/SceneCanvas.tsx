import React from 'react';
import { Canvas } from '@react-three/fiber';
import { NetworkBackground } from './NetworkBackground';
import { Orb } from './Orb';
import { ParticleField } from './ParticleField';
import { useAryaStore } from '../../store/useAryaStore';

export const SceneCanvas: React.FC = () => {
  const voiceState = useAryaStore((s) => s.voiceState);

  return (
    <div className="fixed inset-0 z-0 overflow-hidden bg-[#050505]">
      <Canvas
        camera={{ position: [0, 0, 6.5], fov: 48 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      >
        <ambientLight intensity={0.4} />
        <directionalLight position={[5, 10, 7]} intensity={1.0} color="#ffffff" />

        {/* 1. Fullscreen Shader Background Plane */}
        <React.Suspense fallback={null}>
          <NetworkBackground />
        </React.Suspense>

        {/* 2. Repelling Particle Field */}
        <ParticleField count={1400} />

        {/* 3. Rebuilt Granular Spiky Orb */}
        <Orb voiceState={voiceState} />

        {/* 4. Custom high-performance chromatic dispersion rendered in scene */}
      </Canvas>
    </div>
  );
};
