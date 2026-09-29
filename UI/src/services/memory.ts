import { IMemoryService } from './types';
import { MemoryItem, MemoryCategory } from '../types/arya';
import { generateId } from '../lib/utils';

const INITIAL_MEMORIES: MemoryItem[] = [
  // Personal
  {
    id: 'mem_1',
    category: 'Personal',
    key: 'Favorite Coffee',
    value: 'Oat Milk Flat White with half a shot of vanilla',
    updatedAt: '2 hours ago',
    tags: ['lifestyle', 'preferences'],
  },
  {
    id: 'mem_2',
    category: 'Personal',
    key: 'Gym Schedule',
    value: 'Mon/Wed/Fri 07:00 AM — Strength & Mobility training',
    updatedAt: 'Yesterday',
    tags: ['health', 'fitness'],
  },

  // Work
  {
    id: 'mem_3',
    category: 'Work',
    key: 'Primary Tech Stack',
    value: 'React, TypeScript, Three.js, Node.js, Python, Supabase',
    updatedAt: '3 days ago',
    tags: ['dev', 'tech'],
  },
  {
    id: 'mem_4',
    category: 'Work',
    key: 'Weekly Core Sync',
    value: 'Every Tuesday at 10:00 AM EST with Product Lead',
    updatedAt: '4 days ago',
    tags: ['meeting', 'sync'],
  },
  {
    id: 'mem_5',
    category: 'Work',
    key: 'Quarterly OKRs',
    value: 'Launch Arya v2.0 desktop agent & complete Android low-latency pipeline',
    updatedAt: '1 week ago',
    tags: ['strategy', 'roadmap'],
  },

  // Preferences
  {
    id: 'mem_6',
    category: 'Preferences',
    key: 'Voice Tone Preference',
    value: 'Calm, concise, professional yet warm, high natural cadence',
    updatedAt: 'Today',
    tags: ['arya', 'voice'],
  },
  {
    id: 'mem_7',
    category: 'Preferences',
    key: 'Desktop Layout',
    value: 'Dark theme with glassmorphism UI and particle background',
    updatedAt: '5 days ago',
    tags: ['ui', 'theme'],
  },

  // Contacts
  {
    id: 'mem_8',
    category: 'Contacts',
    key: 'Sarah Vance (Chief Design Officer)',
    value: 'sarah.vance@company.io | Telegram: @sarah_vance',
    updatedAt: '2 days ago',
    tags: ['design', 'lead'],
  },
  {
    id: 'mem_9',
    category: 'Contacts',
    key: 'DevOps Escalation',
    value: 'Marcus Thorne (+1-555-019-9944) — On-call for server outages',
    updatedAt: '1 week ago',
    tags: ['emergency', 'devops'],
  },

  // Important Dates
  {
    id: 'mem_10',
    category: 'Important Dates',
    key: 'Arya v2.0 Beta Release',
    value: 'October 15, 2026 — Keynote & Live Demo',
    updatedAt: 'Just now',
    tags: ['launch', 'deadline'],
  },
  {
    id: 'mem_11',
    category: 'Important Dates',
    key: 'Passport Renewal Notice',
    value: 'Expires November 20, 2026 — Application pending approval',
    updatedAt: '2 weeks ago',
    tags: ['personal', 'travel'],
  },
];

class MockMemoryService implements IMemoryService {
  private memories: MemoryItem[] = [...INITIAL_MEMORIES];

  async getMemories(): Promise<MemoryItem[]> {
    await new Promise((resolve) => setTimeout(resolve, 200));
    return [...this.memories];
  }

  async addMemory(category: MemoryCategory, key: string, value: string, tags?: string[]): Promise<MemoryItem> {
    await new Promise((resolve) => setTimeout(resolve, 300));
    const newItem: MemoryItem = {
      id: generateId('mem'),
      category,
      key,
      value,
      updatedAt: 'Just now',
      tags: tags || ['user-added'],
    };
    this.memories.unshift(newItem);
    return newItem;
  }

  async deleteMemory(id: string): Promise<boolean> {
    await new Promise((resolve) => setTimeout(resolve, 200));
    const initialLen = this.memories.length;
    this.memories = this.memories.filter((item) => item.id !== id);
    return this.memories.length < initialLen;
  }

  async searchMemories(query: string): Promise<MemoryItem[]> {
    await new Promise((resolve) => setTimeout(resolve, 100));
    if (!query.trim()) return [...this.memories];
    const q = query.toLowerCase();
    return this.memories.filter(
      (m) =>
        m.key.toLowerCase().includes(q) ||
        m.value.toLowerCase().includes(q) ||
        m.category.toLowerCase().includes(q) ||
        m.tags?.some((t) => t.toLowerCase().includes(q))
    );
  }
}

export const memoryService = new MockMemoryService();
