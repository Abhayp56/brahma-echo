import { IDesktopAgentService } from './types';
import { DesktopAgentState } from '../types/arya';

class MockDesktopAgentService implements IDesktopAgentService {
  private state: DesktopAgentState = {
    connected: true, // Default connected for mock testing
    version: 'v2.4.0-stable',
    hostname: 'ALEX-WORKSTATION-X1',
    lastHeartbeat: '1s ago',
  };

  async getStatus(): Promise<DesktopAgentState> {
    return { ...this.state };
  }

  async toggleConnection(connected?: boolean): Promise<DesktopAgentState> {
    const nextConnected = connected !== undefined ? connected : !this.state.connected;
    this.state = {
      ...this.state,
      connected: nextConnected,
      lastHeartbeat: nextConnected ? 'Just now' : 'Disconnected',
    };
    return { ...this.state };
  }

  async executeCommand(
    action: 'gods-eye' | 'holographic-board' | 'ai-reader' | 'system-command',
    payload?: any
  ): Promise<{ success: boolean; message: string }> {
    if (!this.state.connected) {
      return {
        success: false,
        message: 'Desktop Agent is not connected. Please enable the Desktop Agent link to control system apps.',
      };
    }

    await new Promise((resolve) => setTimeout(resolve, 500));

    switch (action) {
      case 'gods-eye':
        return {
          success: true,
          message: "Opening God's Eye 360° Process & Visual Inspector on your desktop...",
        };
      case 'holographic-board':
        return {
          success: true,
          message: 'Projecting Holographic Spatial Task Board onto active workspace...',
        };
      case 'ai-reader':
        return {
          success: true,
          message: `Ingesting document "${payload?.fileName || 'Selected Files'}" for deep intent analysis...`,
        };
      default:
        return {
          success: true,
          message: `Desktop Agent executed command "${action}" successfully.`,
        };
    }
  }
}

export const desktopAgentService = new MockDesktopAgentService();
