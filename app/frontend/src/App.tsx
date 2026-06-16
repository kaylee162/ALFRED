import { useEffect, useState } from "react";
import {
  Activity,
  CalendarDays,
  Cpu,
  FolderOpen,
  Radio,
  Send,
  ShieldCheck,
  Sparkles,
  Terminal,
} from "lucide-react";
import "./App.css";

type CalendarEvent = {
  id?: string;
  title: string;
  start: string;
  end?: string;
  location?: string | null;
};

type TomorrowPlan = {
  date: string;
  events: CalendarEvent[];
  free_focus_blocks: {
    start: string;
    end: string;
  }[];
  recommendations: string[];
  suggested_plan: string[];
};

const API_BASE = "http://localhost:8000";

function ClockPanel() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="panel-block clock-panel">
      <p className="panel-label">local time</p>
      <div className="digital-time">
        {now.toLocaleTimeString([], {
          hour: "numeric",
          minute: "2-digit",
          second: "2-digit",
          hour12: true,
        })}
      </div>
      <div className="digital-date">
        {now.toLocaleDateString([], {
          weekday: "long",
          month: "long",
          day: "numeric",
          year: "numeric",
        })}
      </div>
    </div>
  );
}

function App() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("Systems online. Awaiting command.");

  const [calendarConnected, setCalendarConnected] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState("calendar not checked");
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [tomorrowPlan, setTomorrowPlan] = useState<TomorrowPlan | null>(null);

  async function submitCommand() {
    if (!command.trim()) return;

    setResponse("Processing command...");

    try {
      const res = await fetch(`${API_BASE}/command`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ command }),
      });

      const data = await res.json();
      setResponse(data.response);
      setCommand("");
    } catch {
      setResponse("Backend connection failed.");
    }
  }

  async function connectCalendar() {
    setCalendarStatus("connecting...");

    try {
      const res = await fetch(`${API_BASE}/calendar/connect`);
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Calendar connection failed");
      }

      setCalendarConnected(true);
      setCalendarStatus("calendar connected");
      setResponse(data.message || "Google Calendar connected.");
      loadUpcomingEvents();
    } catch (error) {
      setCalendarConnected(false);
      setCalendarStatus("calendar offline");
      setResponse(
        error instanceof Error
          ? error.message
          : "Could not connect Google Calendar."
      );
    }
  }

  async function loadUpcomingEvents() {
    try {
      const res = await fetch(`${API_BASE}/calendar/upcoming?days=7&max_results=5`);
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Could not load calendar events");
      }

      setEvents(data.events || []);
      setCalendarConnected(true);
      setCalendarStatus("calendar synced");
    } catch {
      setCalendarStatus("calendar offline");
    }
  }

  async function loadTomorrowPlan() {
    setResponse("Generating tomorrow's plan...");

    try {
      const res = await fetch(`${API_BASE}/calendar/plan/tomorrow`);
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Could not generate tomorrow plan");
      }

      setTomorrowPlan(data);
      setCalendarConnected(true);
      setCalendarStatus("calendar synced");
      setResponse("Tomorrow's planning summary is ready.");
    } catch (error) {
      setResponse(
        error instanceof Error
          ? error.message
          : "Could not generate tomorrow's plan."
      );
    }
  }

  useEffect(() => {
    loadUpcomingEvents();
  }, []);

  return (
    <main className="alfred-shell">
      <div className="grid-overlay" />
      <div className="scanline" />

      <section className="hud">
        <aside className="side-panel left-panel">
          <div className="panel-block">
            <p className="panel-label">core status</p>
            <div className="status-row">
              <Cpu size={18} />
              <span>local backend active</span>
            </div>
            <div className="status-row">
              <ShieldCheck size={18} />
              <span>confirmations enabled</span>
            </div>
            <div className="status-row">
              <Radio size={18} />
              <span>voice offline</span>
            </div>
            <div className="status-row">
              <CalendarDays size={18} />
              <span>{calendarStatus}</span>
            </div>
          </div>

          <div className="panel-block">
            <p className="panel-label">available tools</p>
            <div className="tool-chip">
              <FolderOpen size={16} />
              <span>project launcher</span>
            </div>
            <div className="tool-chip">
              <FolderOpen size={16} />
              <span>file manager</span>
            </div>
            <div className={calendarConnected ? "tool-chip" : "tool-chip disabled"}>
              <CalendarDays size={16} />
              <span>calendar assistant</span>
            </div>
          </div>
        </aside>

        <section className="center-console">
          <div className="orbit-system">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="orbit orbit-three" />
            <div className="core">
              <Sparkles size={42} />
            </div>
          </div>

          <div className="title-group">
            <h1>A.L.F.R.E.D.</h1>
            <p className="subtitle">
              Adaptive Learning Framework for Responsive Executive Decisions V.3
            </p>
          </div>

          <div className="command-console">
            <div className="console-header">
              <Terminal size={18} />
              <span>command input</span>
            </div>

            <div className="command-input-row">
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitCommand();
                }}
                placeholder='Try: "What should I focus on tomorrow?"'
              />
              <button onClick={submitCommand} aria-label="Send command">
                <Send size={18} />
              </button>
            </div>
          </div>

          <div className="calendar-actions">
            <button onClick={connectCalendar}>Connect Calendar</button>
            <button onClick={loadUpcomingEvents}>Upcoming Events</button>
            <button onClick={loadTomorrowPlan}>Plan Tomorrow</button>
          </div>

          <div className="response-console">
            <p className="panel-label">system response</p>
            <p>{response}</p>
          </div>

          {tomorrowPlan && (
            <div className="response-console plan-console">
              <p className="panel-label">tomorrow focus plan</p>

              <div className="plan-section">
                <strong>Recommendations</strong>
                {tomorrowPlan.recommendations.map((item, index) => (
                  <p key={index}>{item}</p>
                ))}
              </div>

              <div className="plan-section">
                <strong>Open focus blocks</strong>
                {tomorrowPlan.free_focus_blocks.length === 0 ? (
                  <p>No clean focus blocks found.</p>
                ) : (
                  tomorrowPlan.free_focus_blocks.map((block, index) => (
                    <p key={index}>
                      {block.start} - {block.end}
                    </p>
                  ))
                )}
              </div>

              <div className="plan-section">
                <strong>Suggested plan</strong>
                {tomorrowPlan.suggested_plan.map((item, index) => (
                  <p key={index}>
                    {index + 1}. {item}
                  </p>
                ))}
              </div>
            </div>
          )}
        </section>

        <aside className="side-panel right-panel">
          <ClockPanel />

          <div className="panel-block">
            <p className="panel-label">upcoming events</p>

            {events.length === 0 ? (
              <p className="empty-calendar">No events loaded.</p>
            ) : (
              <div className="event-list">
                {events.map((event, index) => (
                  <div className="event-item" key={event.id || index}>
                    <strong>{event.title}</strong>
                    <span>
                      {new Date(event.start).toLocaleString([], {
                        weekday: "short",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </span>
                    {event.location && <small>{event.location}</small>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel-block">
            <p className="panel-label">system load</p>

            <div className="radial-stat">
              <div className="radial-ring">
                <span>{calendarConnected ? "82%" : "24%"}</span>
              </div>
              <p>assistant readiness</p>
            </div>

            <div className="activity-meter">
              <Activity size={18} />
              <span>
                {calendarConnected
                  ? "calendar online · planning enabled"
                  : "agent idle · monitoring input"}
              </span>
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

export default App;