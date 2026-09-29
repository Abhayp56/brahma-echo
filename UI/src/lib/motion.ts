import { Variants, Transition } from 'framer-motion';

export const springConfig: Transition = {
  type: 'spring',
  stiffness: 350,
  damping: 25,
  mass: 0.8,
};

export const gentleSpring: Transition = {
  type: 'spring',
  stiffness: 200,
  damping: 20,
};

export const heavySpring: Transition = {
  type: 'spring',
  stiffness: 400,
  damping: 30,
};

export const bounceSpring: Transition = {
  type: 'spring',
  stiffness: 500,
  damping: 15,
};

export const easeOutExpo = [0.16, 1, 0.3, 1] as const;

// Container stagger variants
export const staggerContainer: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.2,
    },
  },
};

// Panel entrances
export const panelSlideLeft: Variants = {
  hidden: { opacity: 0, x: -50, scale: 0.95 },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 260, damping: 22 },
  },
};

export const panelSlideRight: Variants = {
  hidden: { opacity: 0, x: 50, scale: 0.95 },
  visible: {
    opacity: 1,
    x: 0,
    scale: 1,
    transition: { type: 'spring', stiffness: 260, damping: 22 },
  },
};

export const topBarVariant: Variants = {
  hidden: { opacity: 0, y: -30 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 300, damping: 25 },
  },
};

export const modalVariant: Variants = {
  hidden: { opacity: 0, scale: 0.9, y: 15 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { type: 'spring', stiffness: 380, damping: 26 },
  },
  exit: {
    opacity: 0,
    scale: 0.92,
    y: 10,
    transition: { duration: 0.18, ease: 'easeIn' },
  },
};

export const checkmarkVariant: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: { duration: 0.4, ease: 'easeOut' },
  },
};

export const itemStagger: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.25 } },
};
