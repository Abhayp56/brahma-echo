# Arya — AI Voice Assistant & Digital Secretary UI

Arya is a futuristic, state-of-the-art AI voice assistant and digital secretary interface designed for busy professionals. She controls your desktop, automates complex workflows, and pairs with an Android companion app for natural, phone-call style real-time voice conversations.

---

## 🚀 Tech Stack

- **Framework**: Vite + React 19 + TypeScript
- **3D Graphics**: Three.js via `@react-three/fiber` and `@react-three/drei`
- **Animation**: Framer Motion
- **Styling**: Tailwind CSS v4 (Glassmorphism design system)
- **State Management**: Zustand
- **Icons**: Lucide React
- **QR Codes**: `qrcode.react`

---

## 📁 Project Structure

```
src/
├── components/
│   ├── scene/         # 3D R3F components (Orb, ParticleField, SceneCanvas)
│   ├── layout/        # AppShell, TopBar
│   ├── panels/        # DailyBriefing, SystemMetrics, MemoryBank, Transcript
│   ├── integrations/  # IntegrationsPanel, TelegramModal, WhatsAppModal, AndroidModal
│   ├── actions/       # AIReaderButton, AIReaderModal, GodsEyeButton, HolographicBoardButton
│   ├── chat/          # ChatInput (glass bar with mic toggle & text query)
│   └── ui/            # GlassCard, GlassButton, Modal, Toast, StatusDot
├── store/             # Zustand state management (useAryaStore)
├── services/          # Typed mock services (telegram, whatsapp, android, memory, briefing, metrics, desktopAgent, aiReader)
├── styles/            # Glassmorphism design tokens & Tailwind CSS rules
├── types/             # Domain TypeScript interfaces (arya.ts)
└── lib/               # Utility functions (utils.ts)
```

---

## 🛠️ Architecture & Mock Services

Every feature is decoupled behind a typed TypeScript service interface (`src/services/types.ts`). This allows swapping mock services with real backend endpoints (Supabase, Telegram Webhooks, WhatsApp WebSockets, Native Desktop WebSocket bridge) without changing any UI components.

- **Telegram Bot**: Form validation with bot token, username, chat ID, and instant toast notifications.
- **WhatsApp Headless Bot**: Interactive QR code modal generation with scan simulation.
- **Android Companion App**: Real-time voice stream pairing with QR code & 6-digit PIN.
- **Supabase Memory Bank**: Expandable categories (Personal, Work, Preferences, Contacts, Important Dates) with search, addition, and deletion.
- **System Telemetry**: Real-time CPU, RAM, Disk gauges (active when Desktop Agent is linked) and persistent Neural Link / Network / Latency health indicators.
- **AI Reader & Analyser**: Multi-file drop zone for PDFs and codebases with progressive analysis status.
- **God's Eye & Holographic Board**: Desktop Agent command triggers with status toasts.
- **Live Transcript & Stream Simulator**: Conversation history auto-scrolling with a live stream playback simulator.

---

## ⚡ Getting Started

### Prerequisites
- Node.js 18+
- npm or pnpm or yarn

### Installation

```bash
# Clone repository or navigate to root
cd UI

# Install dependencies (already installed)
npm install
```

### Development Server

Run the dev server:

```bash
npm run dev
```

Open your browser at `http://localhost:5173`.

### Production Build

```bash
npm run build
```

---

## 🎨 Design System

- **Style**: Futuristic, near-black (`#050505`), glassmorphism with subtle silver halos (`rgba(255,255,255,0.12)`).
- **Typography**: Space Grotesk (headings and labels) & JetBrains Mono (metrics and status logs).
- **Accents**: Soft Green (`#22C55E`) for connected states, Soft Red (`#F43F5E`) for errors.
