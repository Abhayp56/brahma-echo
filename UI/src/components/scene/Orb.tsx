import React, { useRef, useMemo, useState, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useAryaStore } from '../../store/useAryaStore';
import { useAudioLevel } from '../../hooks/useAudioLevel';
import { VoiceState } from '../../types/arya';

// ───────────────────────────────────────────────────────────────────
// Constants
// ───────────────────────────────────────────────────────────────────
const ELECTRON_COUNT = 5;
const SPECTRUM_BARS = 64;
const ORBIT_DUST_COUNT = 300;
const TRAIL_LENGTH = 8;
const SHOCKWAVE_POOL = 3;
const PARTICLE_COUNT = 12000;

// Orbit definitions: semi-major, semi-minor, euler tilt, base angular speed
const ORBITS = [
  { a: 1.8, b: 1.1, tilt: [1.05, 0.52, 0] as const, speed: 0.9, style: 'solid' as const },
  { a: 1.95, b: 1.2, tilt: [-1.05, -0.26, 0.78] as const, speed: -1.1, style: 'dashed' as const },
  { a: 1.75, b: 1.25, tilt: [0, 1.05, -0.26] as const, speed: 0.75, style: 'ticked' as const },
];

// Which orbit each electron is initially on + starting angle offset
const ELECTRON_INIT = [
  { ring: 0, offset: 0 },
  { ring: 0, offset: Math.PI },
  { ring: 1, offset: Math.PI * 0.4 },
  { ring: 2, offset: 0 },
  { ring: 2, offset: Math.PI * 0.8 },
];

interface OrbProps {
  voiceState?: VoiceState;
  introProgress?: number; // 0→1, drives draw-in animation
}

// ───────────────────────────────────────────────────────────────────
// Main Orb Component
// ───────────────────────────────────────────────────────────────────
export const Orb: React.FC<OrbProps> = ({ voiceState: propVoiceState, introProgress = 1 }) => {
  const storeVoiceState = useAryaStore((s) => s.voiceState);
  const activeVoiceState: VoiceState = propVoiceState || storeVoiceState;
  const audioLevelsRef = useAudioLevel();

  const [hovered, setHovered] = useState(false);
  const shockwaveRef = useRef({ active: false, progress: 0 });
  const mousePos = useRef({ targetX: 0, targetY: 0 });

  // Prefers-reduced-motion
  const prefersReducedMotion = useRef(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    prefersReducedMotion.current = mq.matches;
    const h = (e: MediaQueryListEvent) => { prefersReducedMotion.current = e.matches; };
    mq.addEventListener?.('change', h);
    return () => mq.removeEventListener?.('change', h);
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      mousePos.current.targetX = (e.clientX / window.innerWidth - 0.5) * 0.35;
      mousePos.current.targetY = -(e.clientY / window.innerHeight - 0.5) * 0.35;
    };
    window.addEventListener('mousemove', onMove);
    return () => window.removeEventListener('mousemove', onMove);
  }, []);

  // ─── Geometries (memoized, disposed on unmount) ───
  const geo = useMemo(() => {
    // Generate a particle swarm for the electron
    const electronPts = 150;
    const elPos = new Float32Array(electronPts * 3);
    for (let i = 0; i < electronPts; i++) {
      const r = Math.cbrt(Math.random()) * 0.07;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      elPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      elPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      elPos[i * 3 + 2] = r * Math.cos(phi);
    }
    const electron = new THREE.BufferGeometry();
    electron.setAttribute('position', new THREE.BufferAttribute(elPos, 3));

    // Generate a smaller particle swarm for the trail
    const trailPts = 40;
    const trPos = new Float32Array(trailPts * 3);
    for (let i = 0; i < trailPts; i++) {
      const r = Math.cbrt(Math.random()) * 0.035;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      trPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      trPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      trPos[i * 3 + 2] = r * Math.cos(phi);
    }
    const trailPt = new THREE.BufferGeometry();
    trailPt.setAttribute('position', new THREE.BufferAttribute(trPos, 3));

    // Orbit ring buffer geometries
    const rings = ORBITS.map((o) => {
      const curve = new THREE.EllipseCurve(0, 0, o.a, o.b, 0, Math.PI * 2, false, 0);
      const pts = curve.getPoints(256);
      return new THREE.BufferGeometry().setFromPoints(pts);
    });

    // Gyroscope outer ring
    const gyroCurve = new THREE.EllipseCurve(0, 0, 2.8, 2.8, 0, Math.PI * 2, false, 0);
    const gyroPts = gyroCurve.getPoints(256);
    const gyroGeo = new THREE.BufferGeometry().setFromPoints(gyroPts);

    // Tick marks for ticked ring and gyroscope
    const tickGeo = new THREE.PlaneGeometry(0.008, 0.06);

    const barGeo = new THREE.PlaneGeometry(0.025, 0.12);

    return { electron, trailPt, rings, gyroGeo, tickGeo, barGeo };
  }, []);

  // ─── Materials (memoized, disposed on unmount) ───
  const mat = useMemo(() => {
    const particleMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.008,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
      depthWrite: false
    });
    const ringMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.35 });
    const dashedMat = new THREE.LineDashedMaterial({ color: 0xffffff, transparent: true, opacity: 0.3, dashSize: 0.15, gapSize: 0.1 });
    const electronMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.008,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
      depthWrite: false
    });
    const trailMats = Array.from({ length: TRAIL_LENGTH }, (_, i) =>
      new THREE.PointsMaterial({
        color: 0xffffff,
        size: 0.006,
        transparent: true,
        opacity: 0.6 * (1 - i / TRAIL_LENGTH),
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
        depthWrite: false
      })
    );
    const gyroMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.15 });
    const tickMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.2, side: THREE.DoubleSide });
    const barMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5, side: THREE.DoubleSide });
    const dustMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.02, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    const shockMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6 });
    const pulseMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.008, transparent: true, opacity: 0.7, blending: THREE.AdditiveBlending });

    return { particleMat, ringMat, dashedMat, electronMat, trailMats, gyroMat, tickMat, barMat, dustMat, shockMat, pulseMat };
  }, []);

  // ─── Particle Data ───
  const [initialPositions, axes, speeds, angles, currentPositions] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const ax = [];
    const sp = new Float32Array(PARTICLE_COUNT);
    const ang = new Float32Array(PARTICLE_COUNT);

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const r = 0.75 + Math.random() * 0.15;
      const theta = Math.random() * 2 * Math.PI;
      const phi = Math.acos(2 * Math.random() - 1);

      const x = r * Math.sin(phi) * Math.cos(theta);
      const y = r * Math.sin(phi) * Math.sin(theta);
      const z = r * Math.cos(phi);

      pos[i * 3] = x;
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = z;

      const pVec = new THREE.Vector3(x, y, z);
      const randVec = new THREE.Vector3(Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5).normalize();
      let axis = new THREE.Vector3().crossVectors(pVec, randVec).normalize();
      if (axis.lengthSq() < 0.001) axis.set(0, 1, 0);
      ax.push(axis);

      sp[i] = (Math.random() * 0.4 + 0.1) * (Math.random() > 0.5 ? 1 : -1);
      ang[i] = 0;
    }
    return [pos, ax, sp, ang, new Float32Array(pos)];
  }, []);

  // ─── Orbit dust positions ───
  const dustPositions = useMemo(() => {
    const arr = new Float32Array(ORBIT_DUST_COUNT * 3);
    for (let i = 0; i < ORBIT_DUST_COUNT; i++) {
      const angle = Math.random() * Math.PI * 2;
      const r = 1.3 + Math.random() * 1.8;
      arr[i * 3] = Math.cos(angle) * r;
      arr[i * 3 + 1] = (Math.random() - 0.5) * 0.4;
      arr[i * 3 + 2] = Math.sin(angle) * r;
    }
    return arr;
  }, []);

  // ─── Shockwave ring geometries (pooled) ───
  const shockGeos = useMemo(() => {
    return Array.from({ length: SHOCKWAVE_POOL }, () => {
      const curve = new THREE.EllipseCurve(0, 0, 1, 1, 0, Math.PI * 2, false, 0);
      return new THREE.BufferGeometry().setFromPoints(curve.getPoints(64));
    });
  }, []);

  // ─── Dispose on unmount ───
  useEffect(() => {
    return () => {
      Object.values(geo).forEach((g) => {
        if (Array.isArray(g)) g.forEach((x) => x.dispose());
        else if (g instanceof THREE.BufferGeometry) g.dispose();
      });
      Object.values(mat).forEach((m) => {
        if (Array.isArray(m)) m.forEach((x) => x.dispose());
        else if (m instanceof THREE.Material) m.dispose();
      });
      shockGeos.forEach((g) => g.dispose());
    };
  }, [geo, mat, shockGeos]);

  // ─── Refs ───
  const groupRef = useRef<THREE.Group>(null);
  const particlesRef = useRef<THREE.Points>(null);
  const particlesGeoRef = useRef<THREE.BufferGeometry>(null);
  const v = useMemo(() => new THREE.Vector3(), []);
  const q = useMemo(() => new THREE.Quaternion(), []);
  const ringGroupRefs = useRef<(THREE.Group | null)[]>([]);
  const gyroRef = useRef<THREE.Group>(null);
  const dustRef = useRef<THREE.Points>(null);
  const spectrumRef = useRef<THREE.Group>(null);
  const specBarRefs = useRef<(THREE.Mesh | null)[]>([]);
  const electronMeshRefs = useRef<(THREE.Points | null)[]>([]);
  const trailMeshRefs = useRef<(THREE.Points | null)[][]>(Array.from({ length: ELECTRON_COUNT }, () => []));
  const shockRingRefs = useRef<(THREE.LineLoop | null)[]>([]);
  const pulseSegRefs = useRef<(THREE.Points | null)[]>([]);

  // ─── Animation state (all ref-based, no React state) ───
  const electronAngles = useRef(ELECTRON_INIT.map((e) => e.offset));
  const electronRings = useRef(ELECTRON_INIT.map((e) => e.ring));

  const d = useRef({
    nucleusScale: 1,
    ringScale: 1,
    ringSpeedMult: 1,
    electronSpeedMult: 1,
    tiltX: 0,
    tiltY: 0,
    spectrumLevel: new Float32Array(SPECTRUM_BARS).fill(0),
    shockwaves: Array.from({ length: SHOCKWAVE_POOL }, () => ({ active: false, progress: 0, scale: 0 })),
    nextShock: 0,
    // Speaking beat shockwaves
    speakBeatTimer: 0,
  });

  const handleClick = (e: any) => {
    e.stopPropagation();
    shockwaveRef.current = { active: true, progress: 0 };
    // Trigger one pooled shockwave ring
    const idx = d.current.nextShock % SHOCKWAVE_POOL;
    d.current.shockwaves[idx] = { active: true, progress: 0, scale: 0.3 };
    d.current.nextShock++;
  };

  // ─── useFrame: all animation logic ───
  useFrame((state, delta) => {
    if (document.hidden) return;
    const time = state.clock.getElapsedTime();
    const sp = prefersReducedMotion.current ? 0.15 : 1.0;
    const lf = Math.min(1, delta * 8);

    // Audio levels
    const al = audioLevelsRef.current || { level: 0, low: 0, mid: 0, high: 0 };

    // Simulated speech envelope
    let sv = 0;
    if (activeVoiceState === 'speaking') {
      sv = Math.abs(Math.sin(time * 7) * Math.cos(time * 3)) * 0.7 + Math.sin(time * 11) * 0.12 + 0.18;
    }

    // ── Target values per state ──
    let tNucleus = 1, tRingScale = 1, tRingSpd = 1, tElSpd = 1.2;
    switch (activeVoiceState) {
      case 'idle':
        tNucleus = 1 + Math.sin(time * 1.5) * 0.03; // heartbeat
        tRingScale = 1; tRingSpd = 1; tElSpd = 1.2;
        break;
      case 'listening':
        tNucleus = 1 + al.level * 0.3;
        tRingScale = 1 + al.low * 0.18;
        tRingSpd = 1 + al.mid * 1.5;
        tElSpd = 1.2 + al.mid * 3;
        break;
      case 'thinking':
        tNucleus = 0.85 + Math.sin(time * 8) * 0.04;
        tRingScale = 0.9 + Math.sin(time * 4) * 0.05;
        tRingSpd = 3.2; tElSpd = 5;
        break;
      case 'speaking':
        tNucleus = 1.05 + sv * 0.25;
        tRingScale = 1.1 + sv * 0.15;
        tRingSpd = 2.2; tElSpd = 4.5;
        break;
    }
    if (hovered) { tNucleus += 0.04; tRingScale += 0.03; }

    // Click shockwave
    let shockImpulse = 0;
    if (shockwaveRef.current.active) {
      shockwaveRef.current.progress += delta * 1.5;
      if (shockwaveRef.current.progress >= 1) {
        shockwaveRef.current.active = false; shockwaveRef.current.progress = 0;
      } else {
        const p = shockwaveRef.current.progress;
        shockImpulse = Math.sin(p * Math.PI) * Math.exp(-p * 2.5);
      }
    }
    tRingScale += shockImpulse * 0.4;
    tElSpd += shockImpulse * 5;

    // Speaking beat shockwaves
    if (activeVoiceState === 'speaking') {
      d.current.speakBeatTimer += delta;
      if (d.current.speakBeatTimer > 0.7 + Math.random() * 0.3) {
        d.current.speakBeatTimer = 0;
        const idx = d.current.nextShock % SHOCKWAVE_POOL;
        d.current.shockwaves[idx] = { active: true, progress: 0, scale: 0.3 };
        d.current.nextShock++;
      }
    }

    // ── Damped lerp ──
    d.current.nucleusScale = THREE.MathUtils.lerp(d.current.nucleusScale, tNucleus, lf);
    d.current.ringScale = THREE.MathUtils.lerp(d.current.ringScale, tRingScale, lf);
    d.current.ringSpeedMult = THREE.MathUtils.lerp(d.current.ringSpeedMult, tRingSpd, lf);
    d.current.electronSpeedMult = THREE.MathUtils.lerp(d.current.electronSpeedMult, tElSpd, lf);
    d.current.tiltX = THREE.MathUtils.lerp(d.current.tiltX, mousePos.current.targetX, lf * 0.4);
    d.current.tiltY = THREE.MathUtils.lerp(d.current.tiltY, mousePos.current.targetY, lf * 0.4);

    // ── Group tilt ──
    if (groupRef.current) {
      groupRef.current.rotation.y = d.current.tiltX * 0.6 + time * 0.03 * sp;
      groupRef.current.rotation.x = d.current.tiltY * 0.6;
      const s = hovered ? 1.04 : 1.0;
      groupRef.current.scale.lerp(new THREE.Vector3(s, s, s), lf);
    }

    // ── Particles (Unknown Order) ──
    if (particlesRef.current && particlesGeoRef.current) {
      particlesRef.current.scale.setScalar(d.current.nucleusScale);
      const partSpd = activeVoiceState === 'speaking' ? 0.8 : activeVoiceState === 'thinking' ? 1.2 : 0.25;

      const posAttr = particlesGeoRef.current.attributes.position;
      const arr = posAttr.array as Float32Array;

      for (let i = 0; i < PARTICLE_COUNT; i++) {
        angles[i] += delta * speeds[i] * partSpd * sp;
        v.set(initialPositions[i * 3], initialPositions[i * 3 + 1], initialPositions[i * 3 + 2]);
        q.setFromAxisAngle(axes[i], angles[i]);
        v.applyQuaternion(q);
        arr[i * 3] = v.x;
        arr[i * 3 + 1] = v.y;
        arr[i * 3 + 2] = v.z;
      }
      posAttr.needsUpdate = true;
    }

    // ── Rings ──
    ringGroupRefs.current.forEach((grp, i) => {
      if (!grp) return;
      const orbit = ORBITS[i];
      grp.rotation.z += delta * orbit.speed * d.current.ringSpeedMult * sp;
      let wobble = 0;
      if (activeVoiceState === 'thinking') wobble = Math.sin(time * 3 + i) * 0.1;
      else if (activeVoiceState === 'speaking') wobble = Math.sin(time * 4 + i * 1.5) * 0.15;
      grp.rotation.x = orbit.tilt[0] + wobble;
      grp.scale.setScalar(d.current.ringScale);
    });

    // ── Pulse segments on rings ──
    pulseSegRefs.current.forEach((seg, i) => {
      if (!seg) return;
      const orbit = ORBITS[i];
      const pulseAngle = time * orbit.speed * d.current.ringSpeedMult * sp * 1.5 + i * 2;
      const px = orbit.a * Math.cos(pulseAngle);
      const py = orbit.b * Math.sin(pulseAngle);
      seg.position.set(px, py, 0);
      const pulseScale = 1 + Math.sin(time * 6 + i) * 0.3;
      seg.scale.setScalar(pulseScale);
    });

    // ── Electrons + trails ──
    const eSp = d.current.electronSpeedMult * sp;
    for (let i = 0; i < ELECTRON_COUNT; i++) {
      const ringIdx = electronRings.current[i];
      const orbit = ORBITS[ringIdx];
      const dir = orbit.speed > 0 ? 1 : -1;
      electronAngles.current[i] += delta * eSp * dir;

      const angle = electronAngles.current[i];
      const ex = orbit.a * Math.cos(angle);
      const ey = orbit.b * Math.sin(angle);

      const eMesh = electronMeshRefs.current[i];
      if (eMesh) {
        eMesh.position.set(ex, ey, 0);
        eMesh.rotation.z += delta * 2;
        eMesh.rotation.y += delta * 1.5;
      }

      // Trail
      const trails = trailMeshRefs.current[i];
      if (trails) {
        const spacing = 0.06 + (eSp > 3 ? 0.04 : 0);
        for (let t = 0; t < trails.length; t++) {
          const tm = trails[t];
          if (!tm) continue;
          const tAngle = angle - (t + 1) * spacing * dir;
          tm.position.set(orbit.a * Math.cos(tAngle), orbit.b * Math.sin(tAngle), 0);
          const sc = 1 - (t + 1) * 0.1;
          tm.scale.setScalar(Math.max(0.1, sc));
          tm.rotation.z -= delta * 1.5;
          tm.rotation.x += delta;
        }
      }
    }

    // ── Gyroscope ring ──
    if (gyroRef.current) {
      gyroRef.current.rotation.x += delta * 0.15 * sp;
      gyroRef.current.rotation.y -= delta * 0.08 * sp;
      gyroRef.current.rotation.z += delta * 0.05 * sp;
    }

    // ── Spectrum ring ──
    if (spectrumRef.current) {
      const sl = d.current.spectrumLevel;
      for (let b = 0; b < SPECTRUM_BARS; b++) {
        let target = 0.02; // almost flat in idle
        if (activeVoiceState === 'listening') {
          const band = b < 20 ? al.low : b < 44 ? al.mid : al.high;
          target = 0.02 + band * 0.35 + Math.sin(time * 8 + b * 0.3) * band * 0.1;
        } else if (activeVoiceState === 'speaking') {
          const band = b < 20 ? sv * 0.8 : b < 44 ? sv : sv * 0.6;
          target = 0.02 + band * 0.35 + Math.sin(time * 10 + b * 0.4) * band * 0.08;
        } else if (activeVoiceState === 'thinking') {
          target = 0.02 + Math.sin(time * 6 + b * 0.5) * 0.08;
        }
        sl[b] = THREE.MathUtils.lerp(sl[b], target, lf * 0.8);

        const bar = specBarRefs.current[b];
        if (bar) {
          bar.scale.y = Math.max(0.1, sl[b] * 6);
          (bar.material as THREE.MeshBasicMaterial).opacity = 0.15 + sl[b] * 2;
        }
      }
    }

    // ── Orbit dust ──
    if (dustRef.current) {
      const dustSpeed = activeVoiceState === 'idle' ? 0.02 : activeVoiceState === 'thinking' ? 0.12 : 0.05;
      dustRef.current.rotation.y += delta * dustSpeed * sp;
    }

    // ── Shockwave pool rings ──
    d.current.shockwaves.forEach((sw, i) => {
      const ring = shockRingRefs.current[i];
      if (!ring) return;
      if (sw.active) {
        sw.progress += delta * 2;
        sw.scale = THREE.MathUtils.lerp(sw.scale, 3.5, delta * 4);
        ring.scale.setScalar(sw.scale);
        (ring.material as THREE.LineBasicMaterial).opacity = Math.max(0, 0.5 * (1 - sw.progress));
        ring.visible = true;
        if (sw.progress >= 1) { sw.active = false; ring.visible = false; }
      } else {
        ring.visible = false;
      }
    });
  });

  // ─── Render ───
  return (
    <group
      ref={groupRef}
      position={[0, 0.2, 0]}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
      onClick={handleClick}
    >
      {/* ─── Nucleus Core (Particles) ─── */}
      <points ref={particlesRef}>
        <bufferGeometry ref={particlesGeoRef}>
          <bufferAttribute
            attach="attributes-position"
            args={[currentPositions, 3]}
            count={PARTICLE_COUNT}
          />
        </bufferGeometry>
        <primitive object={mat.particleMat} attach="material" />
      </points>

      {/* ─── 3 Orbit Rings ─── */}
      {ORBITS.map((orbit, idx) => (
        <group
          key={idx}
          ref={(el) => { ringGroupRefs.current[idx] = el; }}
          rotation={[orbit.tilt[0], orbit.tilt[1], orbit.tilt[2]]}
        >
          {orbit.style === 'dashed' ? (
            <lineLoop geometry={geo.rings[idx]} material={mat.dashedMat} onUpdate={(self) => { self.computeLineDistances(); }} />
          ) : (
            <lineLoop geometry={geo.rings[idx]} material={mat.ringMat} />
          )}

          {/* Tick marks for ticked ring */}
          {orbit.style === 'ticked' && Array.from({ length: 36 }, (_, t) => {
            const angle = (t / 36) * Math.PI * 2;
            const x = orbit.a * Math.cos(angle);
            const y = orbit.b * Math.sin(angle);
            return (
              <mesh
                key={t}
                geometry={geo.tickGeo}
                material={mat.tickMat}
                position={[x, y, 0]}
                rotation={[0, 0, angle + Math.PI / 2]}
              />
            );
          })}

          {/* Pulse segment on ring */}
          <points
            ref={(el) => { pulseSegRefs.current[idx] = el as any; }}
            geometry={geo.electron}
            material={mat.pulseMat}
            scale={1}
          />

          {/* Electrons on this ring */}
          {ELECTRON_INIT.map((ei, eIdx) => {
            if (ei.ring !== idx) return null;
            return (
              <React.Fragment key={`e${eIdx}`}>
                <points
                  ref={(el) => { electronMeshRefs.current[eIdx] = el as any; }}
                  geometry={geo.electron}
                  material={mat.electronMat}
                />
                {/* Comet trail */}
                {Array.from({ length: TRAIL_LENGTH }, (_, t) => (
                  <points
                    key={t}
                    ref={(el) => { if (!trailMeshRefs.current[eIdx]) trailMeshRefs.current[eIdx] = []; trailMeshRefs.current[eIdx][t] = el as any; }}
                    geometry={geo.trailPt}
                    material={mat.trailMats[t]}
                  />
                ))}
              </React.Fragment>
            );
          })}
        </group>
      ))}

      {/* ─── Gyroscope Outer Ring ─── */}
      <group ref={gyroRef} rotation={[0.3, 0, 0.15]}>
        <lineLoop geometry={geo.gyroGeo} material={mat.gyroMat} />
        {/* Fine tick marks around gyroscope */}
        {Array.from({ length: 72 }, (_, t) => {
          const angle = (t / 72) * Math.PI * 2;
          return (
            <mesh
              key={t}
              geometry={geo.tickGeo}
              material={mat.tickMat}
              position={[2.8 * Math.cos(angle), 2.8 * Math.sin(angle), 0]}
              rotation={[0, 0, angle + Math.PI / 2]}
              scale={[1, t % 6 === 0 ? 1.5 : 0.6, 1]}
            />
          );
        })}
      </group>

      {/* ─── Spectrum Ring (audio equalizer) ─── */}
      <group ref={spectrumRef} rotation={[Math.PI / 2, 0, 0]}>
        {Array.from({ length: SPECTRUM_BARS }, (_, b) => {
          const angle = (b / SPECTRUM_BARS) * Math.PI * 2;
          const r = 2.35;
          return (
            <mesh
              key={b}
              ref={(el) => { specBarRefs.current[b] = el; }}
              geometry={geo.barGeo}
              material={mat.barMat}
              position={[r * Math.cos(angle), 0, r * Math.sin(angle)]}
              rotation={[0, -angle + Math.PI / 2, 0]}
              scale={[1, 0.1, 1]}
            />
          );
        })}
      </group>

      {/* ─── Orbit Dust ─── */}
      <points ref={dustRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[dustPositions, 3]}
            count={ORBIT_DUST_COUNT}
          />
        </bufferGeometry>
        <primitive object={mat.dustMat} attach="material" />
      </points>

      {/* ─── Shockwave Pool Rings ─── */}
      {shockGeos.map((sg, i) => (
        <lineLoop
          key={i}
          ref={(el) => { shockRingRefs.current[i] = el; }}
          geometry={sg}
          material={mat.shockMat}
          visible={false}
          rotation={[Math.random() * Math.PI, Math.random() * Math.PI, 0]}
        />
      ))}
    </group>
  );
};
