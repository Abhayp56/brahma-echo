import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

interface ParticleFieldProps {
  count?: number;
}

/**
 * ParticleField — ambient dust particles.
 * Stage 3: Removed cursor-driven repulsion. Particles just drift slowly.
 */
export const ParticleField: React.FC<ParticleFieldProps> = ({ count = 1400 }) => {
  const pointsRef = useRef<THREE.Points>(null);

  // Generate initial static positions
  const [positions, sizes] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const sz = new Float32Array(count);

    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 26;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 20;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 18 - 1;
      sz[i] = Math.random() * 0.04 + 0.015;
    }

    return [pos, sz];
  }, [count]);

  const geoRef = useRef<THREE.BufferGeometry>(null);

  useEffect(() => {
    if (geoRef.current) {
      geoRef.current.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      geoRef.current.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    }
  }, [positions, sizes]);

  useFrame((_state, delta) => {
    if (pointsRef.current) {
      // Slow constant rotation drift only — no cursor interaction
      pointsRef.current.rotation.y += delta * 0.012;
      pointsRef.current.rotation.x += delta * 0.003;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry ref={geoRef} />
      <pointsMaterial
        size={0.035}
        color="#ffffff"
        transparent
        opacity={0.35}
        sizeAttenuation
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
};
