"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = "http://localhost:8000";

type Workspace = { id: number; name: string; prd_text: string };
type Agent = {
  id: number;
  display_name: string;
  agent_type: string;
  status: "online" | "offline";
  connected_at: string;
  last_seen: string;
};
type Task = {
  id: number;
  title: string;
  description: string;
  role: string;
  status: "open" | "claimed" | "in_progress" | "done";
  owner_agent_id: number | null;
};
type Message = { id: number; agent_id: number | null; body: string; created_at: string };
type State = { workspace: Workspace | null; agents: Agent[]; tasks: Task[]; messages: Message[] };

const COLUMNS: Task["status"][] = ["open", "claimed", "in_progress", "done"];
const COLUMN_LABEL: Record<Task["status"], string> = {
  open: "Open",
  claimed: "Claimed",
  in_progress: "In Progress",
  done: "Done",
};
const COLUMN_ACCENT: Record<Task["status"], string> = {
  open: "border-t-zinc-500",
  claimed: "border-t-amber-500",
  in_progress: "border-t-sky-500",
  done: "border-t-emerald-500",
};

const ROLE_STYLE: Record<string, string> = {
  backend: "bg-blue-500/15 text-blue-300 ring-1 ring-blue-500/30",
  frontend: "bg-purple-500/15 text-purple-300 ring-1 ring-purple-500/30",
  testing: "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30",
  devops: "bg-pink-500/15 text-pink-300 ring-1 ring-pink-500/30",
  general: "bg-zinc-500/15 text-zinc-300 ring-1 ring-zinc-500/30",
};
const roleStyle = (role: string) => ROLE_STYLE[role] ?? ROLE_STYLE.general;

const AVATAR_COLORS = [
  "bg-rose-500", "bg-orange-500", "bg-amber-500", "bg-lime-500",
  "bg-emerald-500", "bg-teal-500", "bg-sky-500", "bg-indigo-500",
  "bg-violet-500", "bg-fuchsia-500",
];
const avatarColor = (id: number) => AVATAR_COLORS[id % AVATAR_COLORS.length];
const initials = (name: string) =>
  name.split(/[\s-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("");

function timeAgo(iso: string): string {
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000));
  if (secs < 5) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ago`;
}

function clockTime(iso: string): string {
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function Dashboard() {
  const [state, setState] = useState<State>({ workspace: null, agents: [], tasks: [], messages: [] });
  const [connected, setConnected] = useState(false);
  const [prdOpen, setPrdOpen] = useState(true);
  const [expandedAgent, setExpandedAgent] = useState<number | null>(null);
  const [, forceTick] = useState(0);
  const feedRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/stream`);
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("state", (e) => {
      setConnected(true);
      setState(JSON.parse((e as MessageEvent).data));
    });
    return () => source.close();
  }, []);

  // re-render every 5s so "Xs ago" timestamps and online/offline dots stay fresh
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length]);

  const agent = (id: number | null) => (id === null ? null : state.agents.find((a) => a.id === id) ?? null);
  const agentName = (id: number | null) => (id === null ? "system" : agent(id)?.display_name ?? `agent#${id}`);
  const onlineCount = state.agents.filter((a) => a.status === "online").length;

  if (!state.workspace) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-400 font-mono text-sm">
        No workspace yet — run <code className="mx-1 text-zinc-200">python seed_demo.py</code> in backend/
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-4 sm:p-6 font-sans">
      <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl font-semibold tracking-tight">{state.workspace.name}</h1>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                connected ? "bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30" : "bg-red-500/15 text-red-300 ring-1 ring-red-500/30"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-red-400"}`} />
              {connected ? "Live" : "Disconnected"}
            </span>
          </div>
          <button
            onClick={() => setPrdOpen((v) => !v)}
            className="mt-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            {prdOpen ? "Hide PRD ▲" : "Show PRD ▼"}
          </button>
          {prdOpen && (
            <p className="text-sm text-zinc-400 whitespace-pre-wrap mt-2 max-w-3xl leading-relaxed">
              {state.workspace.prd_text}
            </p>
          )}
        </div>
        <div className="flex gap-4 text-right shrink-0">
          <Stat label="agents" value={`${onlineCount}/${state.agents.length}`} />
          <Stat label="tasks" value={state.tasks.length} />
          <Stat label="messages" value={state.messages.length} />
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_360px] gap-4">
        <section>
          <SectionHeading>Agents</SectionHeading>
          <ul className="space-y-2">
            {state.agents.map((a) => {
                const isOpen = expandedAgent === a.id;
                const ownedTasks = state.tasks.filter((t) => t.owner_agent_id === a.id);
                const ownMessages = state.messages.filter((m) => m.agent_id === a.id).slice(-5).reverse();
                return (
                  <li key={a.id} className="rounded-lg border border-zinc-800 bg-zinc-900 overflow-hidden">
                    <button
                      onClick={() => setExpandedAgent(isOpen ? null : a.id)}
                      className="w-full px-3 py-2 text-sm flex items-center gap-2.5 text-left hover:bg-zinc-800/60 transition-colors"
                    >
                      <div className="relative shrink-0">
                        <div
                          className={`h-7 w-7 rounded-full ${avatarColor(a.id)} flex items-center justify-center text-[11px] font-semibold text-white/90`}
                        >
                          {initials(a.display_name)}
                        </div>
                        <span
                          className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-zinc-900 ${
                            a.status === "online" ? "bg-emerald-400" : "bg-zinc-600"
                          }`}
                        />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate">{a.display_name}</div>
                        <div className="text-xs text-zinc-500">
                          {a.agent_type} · {a.status === "online" ? "online" : `seen ${timeAgo(a.last_seen)}`}
                        </div>
                      </div>
                      <span className="text-zinc-600 text-xs shrink-0">{isOpen ? "▲" : "▼"}</span>
                    </button>
                    {isOpen && (
                      <div className="px-3 pb-3 pt-1 border-t border-zinc-800 text-xs space-y-2.5">
                        <div>
                          <div className="text-[10px] uppercase tracking-wide text-zinc-600 mb-1">
                            Working on ({ownedTasks.length})
                          </div>
                          {ownedTasks.length === 0 && <div className="text-zinc-600 italic">nothing claimed yet</div>}
                          {ownedTasks.map((t) => (
                            <div key={t.id} className="text-zinc-300 leading-snug py-0.5">
                              <span className={`rounded px-1 py-0.5 text-[9px] font-medium mr-1.5 ${roleStyle(t.role)}`}>
                                {t.status}
                              </span>
                              {t.title}
                            </div>
                          ))}
                        </div>
                        <div>
                          <div className="text-[10px] uppercase tracking-wide text-zinc-600 mb-1">Recent activity</div>
                          {ownMessages.length === 0 && <div className="text-zinc-600 italic">no messages yet</div>}
                          {ownMessages.map((m) => (
                            <div key={m.id} className="text-zinc-400 leading-snug py-0.5">
                              <span className="text-zinc-600">{clockTime(m.created_at)}</span> {m.body}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </li>
                );
              })}
            {state.agents.length === 0 && <li className="text-sm text-zinc-600">none connected</li>}
          </ul>
        </section>

        <section>
          <SectionHeading>Task board</SectionHeading>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
            {COLUMNS.map((col) => {
              const items = state.tasks.filter((t) => t.status === col);
              return (
                <div
                  key={col}
                  className={`rounded-lg border border-zinc-800 border-t-2 ${COLUMN_ACCENT[col]} bg-zinc-900/50 p-2.5 min-h-[140px]`}
                >
                  <div className="flex items-center justify-between mb-2.5">
                    <span className="text-xs font-medium text-zinc-400">{COLUMN_LABEL[col]}</span>
                    <span className="text-[11px] text-zinc-600 tabular-nums">{items.length}</span>
                  </div>
                  <div className="space-y-2">
                    {items.map((t) => {
                      const owner = agent(t.owner_agent_id);
                      return (
                        <div
                          key={t.id}
                          className="rounded-md bg-zinc-800/80 border border-zinc-700/50 p-2.5 text-xs hover:border-zinc-600 transition-colors"
                        >
                          <div className="font-medium text-zinc-100 leading-snug">{t.title}</div>
                          {t.description && (
                            <div className="text-zinc-500 mt-1 line-clamp-2">{t.description}</div>
                          )}
                          <div className="flex items-center justify-between mt-2">
                            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${roleStyle(t.role)}`}>
                              {t.role}
                            </span>
                            {owner && (
                              <span className="flex items-center gap-1 text-zinc-500">
                                <span
                                  className={`h-3.5 w-3.5 rounded-full ${avatarColor(owner.id)} flex items-center justify-center text-[8px] font-semibold text-white/90`}
                                >
                                  {initials(owner.display_name)}
                                </span>
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {items.length === 0 && <div className="text-[11px] text-zinc-700 italic py-2">empty</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="min-w-0">
          <SectionHeading>Discussion</SectionHeading>
          <div ref={feedRef} className="space-y-2.5 max-h-[70vh] overflow-y-auto pr-1">
            {state.messages.map((m) => {
              const a = agent(m.agent_id);
              const isSystem = m.agent_id === null;
              return (
                <div
                  key={m.id}
                  className={
                    isSystem
                      ? "text-[11px] text-zinc-600 text-center py-1"
                      : "rounded-lg border border-zinc-800 bg-zinc-900 p-2.5 text-sm"
                  }
                >
                  {isSystem ? (
                    <>— {m.body} —</>
                  ) : (
                    <>
                      <div className="flex items-center gap-1.5 mb-1">
                        <span
                          className={`h-4 w-4 rounded-full ${avatarColor(m.agent_id!)} flex items-center justify-center text-[9px] font-semibold text-white/90`}
                        >
                          {initials(agentName(m.agent_id))}
                        </span>
                        <span className="text-xs font-medium text-zinc-300">{agentName(m.agent_id)}</span>
                        {a && (
                          <span className="text-[10px] text-zinc-600 ml-auto">{clockTime(m.created_at)}</span>
                        )}
                      </div>
                      <div className="text-zinc-200 leading-relaxed">{m.body}</div>
                    </>
                  )}
                </div>
              );
            })}
            {state.messages.length === 0 && <div className="text-sm text-zinc-600">no messages yet</div>}
          </div>
        </section>
      </div>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">{children}</h2>;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-lg font-semibold tabular-nums leading-none">{value}</div>
      <div className="text-[11px] text-zinc-500 mt-0.5">{label}</div>
    </div>
  );
}
