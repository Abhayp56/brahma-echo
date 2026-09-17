/**
 * aryaBridge.js — ARYA AI External Tactical Bridge for God's Eye View
 *
 * Bridges incoming postMessage actions from ARYA Web AI (cloud/web_ui.html)
 * to the internal GEV action runner and Cesium 3D camera/layers.
 */

export function initAryaBridge() {
  if (typeof window === 'undefined') return;

  console.log('🌐 [AryaBridge] Initializing ARYA AI Tactical Recon Bridge...');

  window.addEventListener('message', async (event) => {
    const data = event.data;
    if (!data || typeof data !== 'object') return;

    // 1. Health check ping from ARYA Web AI
    if (data.type === 'gev_ping') {
      const isReady = Boolean(window.__godsEyeView?.viewer);
      window.parent?.postMessage({
        type: 'gev_pong',
        ready: isReady,
        timestamp: Date.now()
      }, '*');
      return;
    }

    // 2. Tactical Recon Action Dispatched by ARYA
    if (data.type === 'gev_action') {
      const { action, args } = data;
      console.log(`🎯 [AryaBridge] Received tactical action: ${action}`, args);

      const runner = window.__godsEyeView?.voiceCommands?.runner;
      if (!runner) {
        console.warn('⚠️ [AryaBridge] GEV action runner not initialized yet');
        window.parent?.postMessage({
          type: 'gev_result',
          action,
          success: false,
          error: 'Tactical runner not ready'
        }, '*');
        return;
      }

      try {
        const result = await runner(action, args || {});
        console.log(`✅ [AryaBridge] Action executed successfully: ${action}`, result);
        window.parent?.postMessage({
          type: 'gev_result',
          action,
          success: true,
          result
        }, '*');
      } catch (err) {
        console.error(`❌ [AryaBridge] Action error for ${action}:`, err);
        window.parent?.postMessage({
          type: 'gev_result',
          action,
          success: false,
          error: String(err.message || err)
        }, '*');
      }
    }
  });

  // Notify parent window that the bridge is mounted and listening
  window.parent?.postMessage({ type: 'gev_bridge_mounted', timestamp: Date.now() }, '*');
}
