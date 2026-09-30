import { IBriefingService } from './types';
import { BriefingData, BriefingTodo } from '../types/arya';
import { generateId } from '../lib/utils';

const INITIAL_BRIEFING: BriefingData = {
  userName: 'Alex Mercer',
  time: '',
  date: '',
  location: 'San Francisco, CA',
  weatherTemp: '71°F',
  weatherCondition: 'Clear & Sunny',
  weatherIcon: 'sun',
  headlines: [
    {
      id: 'news_1',
      title: 'Quantum Computing breakthrough cuts LLM latency by 40%',
      source: 'TechCrunch',
      category: 'AI Tech',
      timeAgo: '25m ago',
    },
    {
      id: 'news_2',
      title: 'Global tech indices rally following Q3 innovation reports',
      source: 'Bloomberg',
      category: 'Finance',
      timeAgo: '1h ago',
    },
    {
      id: 'news_3',
      title: 'Next-gen autonomous desktop agents reach enterprise maturity',
      source: 'Wired',
      category: 'Automation',
      timeAgo: '2h ago',
    },
  ],
  todos: [
    { id: 'todo_1', text: 'Review Q4 Architecture Proposal', completed: false, priority: 'high' },
    { id: 'todo_2', text: 'Approve Telegram bot webhook deployment', completed: true, priority: 'medium' },
    { id: 'todo_3', text: 'Confirm Android Companion voice bitrate settings', completed: false, priority: 'high' },
    { id: 'todo_4', text: 'Sync with Sarah on Glassmorphism UI Polish', completed: false, priority: 'low' },
  ],
  schedule: [
    { id: 'sch_1', time: '10:30 AM', title: 'Product Roadmap Sync', location: 'Virtual Room A', type: 'meeting' },
    { id: 'sch_2', time: '02:00 PM', title: 'Desktop Agent Stress Test', location: 'Dev Environment', type: 'task' },
    { id: 'sch_3', time: '04:15 PM', title: 'Voice Stream Call with Companion App', location: 'Mobile Bridge', type: 'call' },
  ],
};

class MockBriefingService implements IBriefingService {
  private briefing: BriefingData = { ...INITIAL_BRIEFING };

  async getBriefing(): Promise<BriefingData> {
    const now = new Date();
    this.briefing.time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    this.briefing.date = now.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' });

    // Fetch live news from Cloud Brain if available
    try {
      const newsRes = await fetch('/api/news?limit=3');
      if (newsRes.ok) {
        const newsData = await newsRes.json();
        if (Array.isArray(newsData) && newsData.length > 0) {
          this.briefing.headlines = newsData.map((item: any, idx: number) => ({
            id: `news_${idx}`,
            title: item.title || item.headline || 'Breaking News',
            source: item.source || item.author || 'Global News',
            category: item.category || 'Tech',
            timeAgo: item.published_at || 'Recent',
          }));
        }
      }
    } catch (e) {
      // Keep existing headlines on network error
    }

    // Fetch live weather from Cloud Brain if available
    try {
      const weatherRes = await fetch('/api/utility/weather');
      if (weatherRes.ok) {
        const wData = await weatherRes.json();
        if (wData.temperature !== undefined) {
          this.briefing.weatherTemp = `${Math.round(wData.temperature)}°C`;
          this.briefing.weatherCondition = wData.condition || 'Clear Sky';
          if (wData.location) this.briefing.location = wData.location;
        }
      }
    } catch (e) {
      // Keep existing weather on network error
    }

    return { ...this.briefing };
  }

  async toggleTodo(id: string): Promise<boolean> {
    this.briefing.todos = this.briefing.todos.map((todo) =>
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    );
    return true;
  }

  async addTodo(text: string): Promise<BriefingTodo> {
    const newTodo: BriefingTodo = {
      id: generateId('todo'),
      text,
      completed: false,
      priority: 'medium',
    };
    this.briefing.todos.push(newTodo);
    return newTodo;
  }
}

export const briefingService = new MockBriefingService();

