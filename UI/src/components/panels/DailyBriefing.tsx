import React, { useEffect, useState } from 'react';
import { Sun, Calendar, Clock, Newspaper, Plus, MapPin, Square, ChevronDown, Trash2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { GlassCard } from '../ui/GlassCard';
import { useAryaStore } from '../../store/useAryaStore';
import { formatDate, formatTime } from '../../lib/utils';
import { checkmarkVariant } from '../../lib/motion';

/**
 * DailyBriefing — Workable daily briefing panel.
 * Saved once per calendar day in persistent storage.
 * Supports task completion, task deletion, and schedule management.
 */

interface AccordionSectionProps {
  title: string;
  icon: React.ReactNode;
  badge?: string;
  defaultOpen?: boolean;
  action?: React.ReactNode;
  children: React.ReactNode;
}

const AccordionSection: React.FC<AccordionSectionProps> = ({
  title,
  icon,
  badge,
  defaultOpen = false,
  action,
  children,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="border-b border-white/5 last:border-b-0">
      <div className="w-full flex items-center justify-between py-2 px-1 text-xs font-semibold text-zinc-300 uppercase font-sans">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 cursor-pointer hover:text-white transition-colors"
        >
          {icon}
          <span>{title}</span>
          {badge && (
            <span className="text-[9px] font-mono text-zinc-500 normal-case">({badge})</span>
          )}
          <motion.span
            animate={{ rotate: open ? 180 : 0 }}
            transition={{ duration: 0.2 }}
            className="ml-1 inline-block"
          >
            <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />
          </motion.span>
        </button>

        {action && <div>{action}</div>}
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="pb-2 px-1 max-h-44 overflow-y-auto pr-1">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export const DailyBriefing: React.FC = () => {
  const briefing = useAryaStore((s) => s.briefing);
  const loadBriefing = useAryaStore((s) => s.loadBriefing);
  const toggleBriefingTodo = useAryaStore((s) => s.toggleBriefingTodo);
  const addBriefingTodo = useAryaStore((s) => s.addBriefingTodo);
  const deleteBriefingTodo = useAryaStore((s) => s.deleteBriefingTodo);
  const addBriefingSchedule = useAryaStore((s) => s.addBriefingSchedule);

  const [currentTime, setCurrentTime] = useState(formatTime());
  const [currentDate, setCurrentDate] = useState(formatDate());
  const [newTodoText, setNewTodoText] = useState('');
  const [showAddTodo, setShowAddTodo] = useState(false);

  const [showAddSchedule, setShowAddSchedule] = useState(false);
  const [schTime, setSchTime] = useState('10:00 AM');
  const [schTitle, setSchTitle] = useState('');
  const [schLocation, setSchLocation] = useState('');

  useEffect(() => {
    loadBriefing();
    const interval = setInterval(() => {
      setCurrentTime(formatTime());
      setCurrentDate(formatDate());
    }, 1000);
    return () => clearInterval(interval);
  }, [loadBriefing]);

  const handleAddTodoSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (newTodoText.trim()) {
      addBriefingTodo(newTodoText.trim());
      setNewTodoText('');
      setShowAddTodo(false);
    }
  };

  const handleAddScheduleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (schTitle.trim()) {
      addBriefingSchedule(schTime, schTitle.trim(), schLocation.trim());
      setSchTitle('');
      setSchLocation('');
      setShowAddSchedule(false);
    }
  };

  if (!briefing) return null;

  return (
    <GlassCard
      title="Daily Briefing"
      icon={<Calendar className="w-4 h-4 text-white" />}
      action={
        <div className="flex items-center gap-1.5 text-xs font-mono text-zinc-400">
          <MapPin className="w-3 h-3 text-zinc-400" />
          <span>{briefing.location}</span>
        </div>
      }
      className="w-full flex-shrink-0"
    >
      <div className="space-y-0">
        {/* Clock & Weather — always visible */}
        <div className="glass-panel p-2.5 rounded-xl border-white/10 flex items-center justify-between mb-2">
          <div>
            <div className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
              <Clock className="w-3.5 h-3.5 text-zinc-300" />
              <AnimatePresence mode="wait">
                <motion.span
                  key={currentTime}
                  initial={{ opacity: 0.6, y: -2 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2 }}
                  className="font-mono text-sm"
                >
                  {currentTime}
                </motion.span>
              </AnimatePresence>
            </div>
            <div className="text-[10px] text-zinc-400 font-mono mt-0.5">{currentDate}</div>
          </div>
          <div className="text-right flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-300">
              <Sun className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-bold text-white">{briefing.weatherTemp}</div>
              <div className="text-[9px] text-zinc-400 font-mono">{briefing.weatherCondition}</div>
            </div>
          </div>
        </div>

        {/* Schedule Section */}
        <AccordionSection
          title="Schedule"
          icon={<Clock className="w-3.5 h-3.5 text-zinc-400" />}
          badge={`${briefing.schedule.length}`}
          defaultOpen={true}
          action={
            <button
              onClick={() => setShowAddSchedule(!showAddSchedule)}
              className="text-[10px] text-zinc-400 hover:text-white flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Plus className="w-3 h-3" />
              <span>Event</span>
            </button>
          }
        >
          {showAddSchedule && (
            <form onSubmit={handleAddScheduleSubmit} className="mb-2 space-y-1.5 glass-panel p-2 rounded-lg border-white/10">
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={schTime}
                  onChange={(e) => setSchTime(e.target.value)}
                  placeholder="Time (e.g. 10:00 AM)"
                  className="glass-input w-24 px-2 py-1 rounded text-[10px] font-mono"
                />
                <input
                  type="text"
                  value={schTitle}
                  onChange={(e) => setSchTitle(e.target.value)}
                  placeholder="Event title..."
                  className="glass-input flex-1 px-2 py-1 rounded text-[10px]"
                  autoFocus
                />
              </div>
              <div className="flex items-center gap-1.5">
                <input
                  type="text"
                  value={schLocation}
                  onChange={(e) => setSchLocation(e.target.value)}
                  placeholder="Location / Link (optional)"
                  className="glass-input flex-1 px-2 py-1 rounded text-[10px]"
                />
                <button type="submit" className="px-2 py-1 rounded bg-white text-black font-semibold text-[10px] cursor-pointer">
                  Save
                </button>
              </div>
            </form>
          )}

          {briefing.schedule.length === 0 ? (
            <div className="text-[10px] text-zinc-500 font-mono py-2 text-center">
              No events scheduled today.
            </div>
          ) : (
            <div className="space-y-1.5">
              {briefing.schedule.map((item) => (
                <div
                  key={item.id}
                  className="glass-panel p-2 rounded-lg border-white/10 text-xs flex items-center justify-between hover:bg-white/10 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="px-1.5 py-0.5 rounded bg-white/10 text-[9px] font-mono text-zinc-300 shrink-0">
                      {item.time}
                    </span>
                    <span className="text-white font-medium truncate text-[11px]">{item.title}</span>
                  </div>
                  {item.location && (
                    <span className="text-[9px] text-zinc-400 font-mono shrink-0 ml-2">
                      {item.location}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </AccordionSection>

        {/* Tasks Section */}
        <AccordionSection
          title="Tasks"
          icon={<Calendar className="w-3.5 h-3.5 text-zinc-400" />}
          badge={`${briefing.todos.filter((t) => !t.completed).length}`}
          defaultOpen={true}
          action={
            <button
              onClick={() => setShowAddTodo(!showAddTodo)}
              className="text-[10px] text-zinc-400 hover:text-white flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Plus className="w-3 h-3" />
              <span>Task</span>
            </button>
          }
        >
          {showAddTodo && (
            <form onSubmit={handleAddTodoSubmit} className="mb-2 flex items-center gap-2">
              <input
                type="text"
                value={newTodoText}
                onChange={(e) => setNewTodoText(e.target.value)}
                placeholder="New task..."
                autoFocus
                className="glass-input flex-1 px-2 py-1 rounded-lg text-[11px]"
              />
              <button type="submit" className="px-2 py-1 rounded-lg bg-white text-black font-semibold text-[11px] cursor-pointer">
                Save
              </button>
            </form>
          )}

          {briefing.todos.length === 0 ? (
            <div className="text-[10px] text-zinc-500 font-mono py-2 text-center">
              All tasks completed! Click '+ Task' to add more.
            </div>
          ) : (
            <div className="space-y-1">
              {briefing.todos.map((todo) => (
                <div
                  key={todo.id}
                  className="glass-panel p-2 rounded-lg border-white/10 text-[11px] flex items-center justify-between group hover:bg-white/10 transition-colors"
                >
                  <div
                    onClick={() => toggleBriefingTodo(todo.id)}
                    className="flex items-center gap-2 flex-1 cursor-pointer min-w-0"
                  >
                    {todo.completed ? (
                      <div className="w-3.5 h-3.5 rounded bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center shrink-0">
                        <svg className="w-2.5 h-2.5 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <motion.path d="M20 6L9 17l-5-5" variants={checkmarkVariant} initial="hidden" animate="visible" />
                        </svg>
                      </div>
                    ) : (
                      <Square className="w-3.5 h-3.5 text-zinc-400 shrink-0" />
                    )}
                    <motion.span
                      animate={{ opacity: todo.completed ? 0.5 : 1 }}
                      className={`truncate ${todo.completed ? 'line-through text-zinc-400' : 'text-zinc-200'}`}
                    >
                      {todo.text}
                    </motion.span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0 ml-2">
                    {todo.priority && (
                      <span className={`text-[8px] px-1 py-0.5 rounded font-mono uppercase ${
                        todo.priority === 'high' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : todo.priority === 'medium' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                        : 'bg-white/10 text-zinc-300'
                      }`}>
                        {todo.priority}
                      </span>
                    )}
                    <button
                      onClick={() => deleteBriefingTodo(todo.id)}
                      className="opacity-0 group-hover:opacity-100 p-0.5 text-zinc-500 hover:text-rose-400 transition-opacity cursor-pointer"
                      title="Delete task"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </AccordionSection>

        {/* Intelligence / News Section */}
        <AccordionSection
          title="Intelligence"
          icon={<Newspaper className="w-3.5 h-3.5 text-zinc-400" />}
          badge={`${briefing.headlines.length}`}
        >
          <div className="space-y-1">
            {briefing.headlines.map((news) => (
              <div key={news.id} className="glass-panel p-2 rounded-lg border-white/10 text-[11px] flex items-center justify-between">
                <span className="text-zinc-300 font-medium truncate flex-1 pr-2">{news.title}</span>
                <span className="text-[9px] text-zinc-400 font-mono shrink-0">{news.source}</span>
              </div>
            ))}
          </div>
        </AccordionSection>
      </div>
    </GlassCard>
  );
};
