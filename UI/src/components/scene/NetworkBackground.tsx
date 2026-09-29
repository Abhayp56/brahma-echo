import React, { useRef, useMemo, useEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

// Fallback 2x2 dark canvas texture so GLSL uniform sampler2D uTexture is NEVER null
const createFallbackTexture = () => {
  const canvas = document.createElement('canvas');
  canvas.width = 2;
  canvas.height = 2;
  const ctx = canvas.getContext('2d')!;
  ctx.fillStyle = '#08080c';
  ctx.fillRect(0, 0, 2, 2);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
};

/**
 * NetworkBackground — fullscreen shader background plane.
 * Stage 3: Removed wireframe grid overlay, cursor spotlight, cursor-driven mesh push.
 * Kept: slow constant drift, vignette, very subtle mouse parallax (damped).
 * Grid/mesh lines from the texture are dimmed in shader.
 */
export const NetworkBackground: React.FC = () => {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const { viewport, size } = useThree();

  const textureRef = useRef<THREE.Texture>(createFallbackTexture());
  // Very subtle parallax offset from mouse (not spotlight)
  const mousePos = useRef({ targetX: 0.5, targetY: 0.5, currentX: 0.5, currentY: 0.5 });

  useEffect(() => {
    const img = new Image();
    img.src = '/assets/bg-network.jpg';
    img.onload = () => {
      const tex = new THREE.Texture(img);
      tex.needsUpdate = true;
      tex.minFilter = THREE.LinearFilter;
      tex.magFilter = THREE.LinearFilter;
      textureRef.current = tex;
      if (materialRef.current) {
        materialRef.current.uniforms.uTexture.value = tex;
      }
    };
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      mousePos.current.targetX = e.clientX / window.innerWidth;
      mousePos.current.targetY = 1.0 - e.clientY / window.innerHeight;
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  const uniforms = useMemo(
    () => ({
      uTexture: { value: textureRef.current },
      uTime: { value: 0 },
      uParallax: { value: new THREE.Vector2(0, 0) },
      uAspect: { value: size.width / size.height },
    }),
    [size]
  );

  // Vertex shader: slow drift waves only, no cursor push
  const vertexShader = `
    varying vec2 vUv;
    uniform float uTime;

    void main() {
      vUv = uv;
      vec3 pos = position;

      // Gentle constant drift waves
      float wave1 = sin(pos.x * 0.6 + uTime * 0.3) * cos(pos.y * 0.6 + uTime * 0.25) * 0.25;
      float wave2 = sin(pos.x * 1.2 - uTime * 0.35) * 0.1;
      pos.z += wave1 + wave2;

      gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(pos, 1.0);
    }
  `;

  // Fragment shader: dim mesh/grid lines, keep depth/vignette, no cursor spotlight
  const fragmentShader = `
    uniform sampler2D uTexture;
    uniform float uTime;
    uniform vec2 uParallax;
    uniform float uAspect;
    varying vec2 vUv;

    void main() {
      // Very subtle parallax UV shift
      vec2 uv = vUv + uParallax * 0.008;
      vec4 texColor = texture2D(uTexture, uv);

      // Calculate luminance to detect bright grid lines and dim them
      float lum = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));
      // Clamp bright lines: anything above threshold gets darkened
      float lineDim = smoothstep(0.25, 0.55, lum);
      texColor.rgb *= mix(1.0, 0.25, lineDim);

      // Dark sci-fi vignette
      vec2 vignUv = (vUv - 0.5) * 1.6;
      float vignette = 1.0 - dot(vignUv, vignUv);
      vignette = smoothstep(0.0, 0.85, vignette);

      vec3 baseBg = vec3(0.02, 0.02, 0.035);
      vec3 metallicGlow = vec3(0.06, 0.065, 0.085) * (1.0 + texColor.r * 0.8);

      vec3 finalColor = mix(baseBg, metallicGlow, texColor.r * 0.5 + 0.15);
      finalColor *= vignette;

      gl_FragColor = vec4(finalColor, 1.0);
    }
  `;

  useFrame((state) => {
    const time = state.clock.getElapsedTime();
    // Very heavily damped parallax (just subtle depth)
    mousePos.current.currentX = THREE.MathUtils.lerp(mousePos.current.currentX, mousePos.current.targetX, 0.02);
    mousePos.current.currentY = THREE.MathUtils.lerp(mousePos.current.currentY, mousePos.current.targetY, 0.02);

    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value = time;
      materialRef.current.uniforms.uParallax.value.set(
        (mousePos.current.currentX - 0.5),
        (mousePos.current.currentY - 0.5)
      );
      materialRef.current.uniforms.uAspect.value = size.width / size.height;
    }

    if (meshRef.current) {
      meshRef.current.rotation.z = Math.sin(time * 0.08) * 0.01;
    }
  });

  return (
    <group position={[0, 0, -4]}>
      {/* Background shader plane — no wireframe overlay */}
      <mesh ref={meshRef}>
        <planeGeometry args={[viewport.width * 1.6, viewport.height * 1.6, 32, 32]} />
        <shaderMaterial
          ref={materialRef}
          uniforms={uniforms}
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          wireframe={false}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
};
