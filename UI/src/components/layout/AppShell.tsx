import React from 'react';
import { motion } from 'framer-motion';
import { TopBar } from './TopBar';
import { SceneCanvas } from '../scene/SceneCanvas';
import { DailyBriefing } from '../panels/DailyBriefing';
import { SystemMetrics } from '../panels/SystemMetrics';
import { Transcript } from '../panels/Transcript';
import { ChatInput } from '../chat/ChatInput';
import { AIReaderButton, AIReaderModal } from '../actions/AIReaderModal';
import { GodsEyeButton } from '../actions/GodsEyeButton';
import { HolographicBoardButton } from '../actions/HolographicBoardButton';
import { IntegrationsPanel } from '../integrations/IntegrationsPanel';
import { TelegramModal } from '../integrations/TelegramModal';
import { WhatsAppModal } from '../integrations/WhatsAppModal';
import { AndroidModal } from '../integrations/AndroidModal';
import { ToastContainer } from '../ui/Toast';
import { staggerContainer, panelSlideLeft, panelSlideRight, topBarVariant } from '../../lib/motion';

/**
 * AppShell — root layout.
 * Supabase memory card removed. Live Transcript expanded to full column height.
 */
export const AppShell: React.FC = () => {
  return (
    <div className="relative h-screen w-full overflow-hidden text-zinc-100 font-sans selection:bg-white/20 selection:text-white">
      {/* 3D Scene Background Canvas */}
      <SceneCanvas />

      {/* Top Navigation Bar */}
      <TopBar />

      {/* Main Grid Workspace with Staggered Intro Sequence */}
      <motion.main
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="relative z-10 pt-20 pb-4 px-4 sm:px-6 max-w-[1600px] mx-auto h-[calc(100vh-0px)] flex flex-col"
      >
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch flex-1 min-h-0">
          {/* Left Column: Accordion panels (no outer scroll) */}
          <motion.div
            variants={panelSlideLeft}
            className="lg:col-span-3 flex flex-col gap-3 order-2 lg:order-1 min-h-0 overflow-hidden"
          >
            <DailyBriefing />
            <SystemMetrics />
          </motion.div>

          {/* Center Column: Orb Workspace & Quick Actions */}
          <div className="lg:col-span-6 flex flex-col items-center justify-between min-h-0 py-2 order-1 lg:order-2 gap-4">
            {/* Action Buttons */}
            <motion.div variants={topBarVariant} className="flex flex-wrap items-center justify-center gap-3">
              <AIReaderButton />
              <GodsEyeButton />
              <HolographicBoardButton />
            </motion.div>

            {/* Spacer for 3D Orb */}
            <div className="flex-1 w-full flex items-center justify-center min-h-[180px]" />

            {/* Bottom Glass Chat Bar */}
            <motion.div variants={topBarVariant} className="w-full">
              <ChatInput />
            </motion.div>
          </div>

          {/* Right Column: Live Conversation Transcript (Expanded to fill entire column) */}
          <motion.div
            variants={panelSlideRight}
            className="lg:col-span-3 flex flex-col gap-3 order-3 min-h-0 h-full overflow-hidden"
          >
            <Transcript />
          </motion.div>
        </div>
      </motion.main>

      {/* Modals & Dialogs */}
      <IntegrationsPanel />
      <TelegramModal />
      <WhatsAppModal />
      <AndroidModal />
      <AIReaderModal />

      {/* Toast Feedback */}
      <ToastContainer />
    </div>
  );
};
