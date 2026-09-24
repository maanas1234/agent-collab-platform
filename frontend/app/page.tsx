"use client";

import { useEffect, useState } from "react";

const API_BASE = "http://localhost:8000";

type Workspace = { id: number; name: string; prd_text: string };
type Agent = { id: number; display_name: string; agent_type: string; status: string };
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

export default function Dashboard() {
  const [state, setState] = useState<State>({ workspace: null, agents: [], tasks: [], messages: [] });

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/stream`);
    source.addEventListener("state", (e) => setState(JSON.parse((e as MessageEvent).data)));
    return () => source.close();
  }, []);

  const agentName = (id: number | null) =>
    id === null ? "system" : state.agents.find((a) => a.id === id)?.display_name ?? `agent#${id}`;

  if (!state.workspace) {
    return (
      <div className="min-h-screen flex items-center justify-center text-zinc-400 font-mono">
        No workspace yet — run <code className="mx-1 text-zinc-200">python seed_demo.py</code> in backend/
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 font-sans">
      <header className="mb-6">
        <h1 className="text-xl font-semibold">{state.workspace.name}</h1>
        <p className="text-sm text-zinc-400 whitespace-pre-wrap mt-1 max-w-3xl">{state.workspace.prd_text}</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[220px_1fr_360px] gap-4">
        <section>
          <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Agents online</h2>
          <ul className="space-y-2">
            {state.agents.map((a) => (
              <li key={a.id} className="rounded border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  {a.display_name}
                </div>
                <div className="text-xs text-zinc-500">{a.agent_type}</div>
              </li>
            ))}
            {state.agents.length === 0 && <li className="text-sm text-zinc-600">none connected</li>}
          </ul>
        </section>

        <section>
          <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Task board</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {COLUMNS.map((col) => (
              <div key={col} className="rounded border border-zinc-800 bg-zinc-900/50 p-2 min-h-[120px]">
                <div className="text-xs font-medium text-zinc-400 mb-2">{COLUMN_LABEL[col]}</div>
                <div className="space-y-2">
                  {state.tasks
                    .filter((t) => t.status === col)
                    .map((t) => (
                      <div key={t.id} className="rounded bg-zinc-800 p-2 text-xs">
                        <div className="font-medium">{t.title}</div>
                        <div className="text-zinc-400 mt-1">{t.role}</div>
                        {t.owner_agent_id !== null && (
                          <div className="text-zinc-500 mt-1">owner: {agentName(t.owner_agent_id)}</div>
                        )}
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Discussion</h2>
          <div className="space-y-2 max-h-[70vh] overflow-y-auto">
            {state.messages.map((m) => (
              <div key={m.id} className="rounded border border-zinc-800 bg-zinc-900 p-2 text-sm">
                <div className="text-xs text-zinc-500">{agentName(m.agent_id)}</div>
                <div>{m.body}</div>
              </div>
            ))}
            {state.messages.length === 0 && <div className="text-sm text-zinc-600">no messages yet</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
