import { useEffect, useState } from "react";
import {
  Activity,
  CalendarDays,
  ChevronDown,
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

function parseCalendarResponse(response: string) {
  const isDailyCalendar =
    response.startsWith("Here’s your calendar for") ||
    response.startsWith("No events") ||
    response.startsWith("You have nothing on your calendar");

  const isWeeklyCalendar = response.startsWith("Weekly Calendar Overview");

  if (!isDailyCalendar && !isWeeklyCalendar) return null;

    if (isWeeklyCalendar) {
    const lines = response.split("\n");

    const weekItems: {
      date: string;
      dateShort: string;
      weekday: string;
      countText: string;
      events: {
        time: string;
        title: string;
        location?: string;
      }[];
    }[] = [];

    let currentDay: (typeof weekItems)[number] | null = null;

    lines.forEach((rawLine) => {
      const line = rawLine.trim();

      const dayMatch = line.match(
        /^•\s*(\d{4}-\d{2}-\d{2})\s*—\s*(\d+ events?)/i
      );

      if (dayMatch) {
        const date = dayMatch[1];
        const countText = dayMatch[2];

        const parsedDate = new Date(`${date}T12:00:00`);

        currentDay = {
          date,
          dateShort: parsedDate.toLocaleDateString([], {
            month: "2-digit",
            day: "2-digit",
          }),
          weekday: parsedDate.toLocaleDateString([], {
            weekday: "long",
          }),
          countText,
          events: [],
        };

        weekItems.push(currentDay);
        return;
      }

      if (!currentDay) return;

      const eventMatch = line.match(/^-\s*(.+?)\s*—\s*(.+)$/);

      if (eventMatch) {
        const time = eventMatch[1];
        const rest = eventMatch[2];

        if (rest.toLowerCase() === "no events") return;

        const [title, location] = rest.split(" at ");

        currentDay.events.push({
          time,
          title: title || "Untitled",
          location,
        });
      }
    });

    const summaryItems = lines
      .map((line) => line.trim())
      .filter((line) => line.startsWith("•") && line.includes(":") && !line.includes("—"))
      .map((line) => line.replace("•", "").trim());

    return {
      type: "weekly" as const,
      title: "Weekly Calendar Overview",
      events: [],
      weekItems,
      summaryItems,
    };
  }

  if (
    response.startsWith("No events") ||
    response.startsWith("You have nothing")
  ) {
    return {
      type: "daily" as const,
      title: response,
      events: [],
      weekItems: [],
      summaryItems: [],
    };
  }

  const [heading, ...lines] = response.split("\n");

  const events = lines
    .filter((line) => line.trim().startsWith("•"))
    .map((line) => {
      const clean = line.replace(/^[-•]\s*/, "").trim();
      const [time, rest] = clean.split(" — ");
      const [title, location] = rest?.split(" at ") ?? ["Untitled"];

      return {
        time: time || "All day",
        title: title || "Untitled",
        location,
      };
    });

  return {
    type: "daily" as const,
    title: heading,
    events,
    weekItems: [],
    summaryItems: [],
  };
}

function ChatCalendarResponse({ response }: { response: string }) {
  const parsed = parseCalendarResponse(response);
  const [openDayIndex, setOpenDayIndex] = useState<number | null>(null);

  if (!parsed) {
    return <p>{response}</p>;
  }

  if (parsed.type === "weekly") {
    return (
      <div className="chat-calendar-card">
        <div className="chat-calendar-header centered">
          <div>
            <p className="panel-label">calendar response</p>
            <h3>Week Overview</h3>
          </div>
          <CalendarDays size={18} />
        </div>

        <div className="chat-week-list">
          {parsed.weekItems.map((day, index) => {
            const isOpen = openDayIndex === index;

            return (
              <div className="chat-week-day" key={day.date}>
                <div className="chat-week-row">
                  <span className="chat-week-date">{day.dateShort}</span>
                  <strong className="chat-week-name">{day.weekday}</strong>

                  <button
                    className={`chat-week-toggle ${isOpen ? "open" : ""}`}
                    onClick={() => setOpenDayIndex(isOpen ? null : index)}
                    type="button"
                  >
                    <span>{day.countText}</span>
                    <ChevronDown size={15} />
                  </button>
                </div>

                {isOpen && (
                  <div className="chat-week-dropdown">
                    {day.events.length === 0 ? (
                      <small>No events for {day.weekday}.</small>
                    ) : (
                      day.events.map((event, eventIndex) => (
                        <div className="chat-week-event-row" key={eventIndex}>
                          <span>{event.time}</span>
                          <strong>{event.title}</strong>
                          {event.location && <small>{event.location}</small>}
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {parsed.summaryItems.length > 0 && (
          <div className="chat-week-summary">
            <span>Summary</span>
            {parsed.summaryItems.map((item, index) => (
              <small key={index}>{item}</small>
            ))}
          </div>
        )}
      </div>
    );
  }

  const displayTitle = parsed.title
    .replace("Here’s your calendar for ", "")
    .replace(":", "");

  return (
    <div className="chat-calendar-card">
      <div className="chat-calendar-header centered">
        <div>
          <p className="panel-label">calendar response</p>
          <h3>{displayTitle}</h3>
        </div>
        <CalendarDays size={18} />
      </div>

      {parsed.events.length === 0 ? (
        <div className="chat-calendar-empty">
          <span>{parsed.title}</span>
          <small>Your schedule is clear for this window.</small>
        </div>
      ) : (
        <div className="chat-calendar-list">
          {parsed.events.map((event, index) => (
            <div className="chat-calendar-event" key={index}>
              <div className="chat-calendar-time">{event.time}</div>

              <div className="chat-calendar-details">
                <strong>{event.title}</strong>
                {event.location && <small>{event.location}</small>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function App() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("Systems online. Awaiting command.");

  const [calendarConnected, setCalendarConnected] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState("calendar not checked");
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [tomorrowPlan] = useState<TomorrowPlan | null>(null);

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
                placeholder='Try: "Whats on my calendar today?"'
              />
              <button onClick={submitCommand} aria-label="Send command">
                <Send size={18} />
              </button>
            </div>
          </div>

          <div className="response-console">
            <p className="panel-label">system response</p>
            <ChatCalendarResponse response={response} />
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

          <div className="panel-block events-panel">
            <div className="events-panel-header">
              <div>
                <p className="panel-label">upcoming events</p>
                <h3>Next on deck</h3>
              </div>
              <CalendarDays size={22} />
            </div>

            {events.length === 0 ? (
              <div className="empty-calendar-card">
                <span>No events loaded.</span>
                <small>Sync your calendar to view upcoming plans.</small>
              </div>
            ) : (
              <div className="event-list">
                {events.slice(0, 3).map((event, index) => (
                  <div className="event-item" key={event.id || index}>
                    <div className="event-time-badge">
                      {new Date(event.start).toLocaleDateString([], {
                        weekday: "short",
                      })}
                      <strong>
                        {new Date(event.start).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </strong>
                    </div>

                    <div className="event-details">
                      <strong>{event.title}</strong>
                      <span>
                        {new Date(event.start).toLocaleDateString([], {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                      {event.location && <small>{event.location}</small>}
                    </div>
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