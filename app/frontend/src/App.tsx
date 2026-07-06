import { type FormEvent, useEffect, useState } from "react";
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

import {
  createCalendarEvent,
  createCalendarEventFromForm,
  updateCalendarEvent,
} from "./api/calendarApi";
import "./App.css";

type ProjectItem = {
  name: string;
  path: string;
  type: "folder" | "file";
  can_open?: boolean;
};

type ProjectExplorerData = {
  success: boolean;
  message: string;
  root?: string;
  current_path?: string;
  parent_path?: string | null;
  items: ProjectItem[];
};

type CalendarEvent = {
  id?: string;
  title: string;
  start: string;
  end?: string;
  location?: string | null;
  description?: string | null;
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


type EditableCalendarEvent = {
  id: string;
  title: string;
  start: string;
  end: string;
  location?: string | null;
  description?: string | null;
};

type PendingCalendarEvent = {
  missing_fields: ("title" | "date" | "time")[];
  draft: {
    title?: string;
    date?: string;
    start_time?: string;
    end_time?: string;
    start?: string;
    end?: string;
    location?: string | null;
    description?: string | null;
  };
};

function toDateTimeLocalValue(value?: string | null) {
  if (!value) return "";

  const cleanedValue = value.includes("T")
    ? value
    : value.replace(" ", "T");

  const date = new Date(cleanedValue);
  if (Number.isNaN(date.getTime())) return "";

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function normalizeEditableEvent(raw: any): EditableCalendarEvent | null {
  if (!raw) return null;

  const start =
    typeof raw.start === "string"
      ? raw.start
      : raw.start?.dateTime || raw.start?.date || raw.start_time;

  const end =
    typeof raw.end === "string"
      ? raw.end
      : raw.end?.dateTime || raw.end?.date || raw.end_time;

  if (!raw.id || !start) return null;

  return {
    id: raw.id,
    title: raw.title || raw.summary || "Untitled",
    start,
    end,
    location: raw.location || null,
    description: raw.description || null,
  };
}

function getCreatedEventFromResponse(response: string): EditableCalendarEvent | null {
  const match = response.match(/__ALFRED_CALENDAR_EVENT__=(.+)$/m);
  if (!match) return null;

  try {
    return normalizeEditableEvent(JSON.parse(match[1]));
  } catch {
    return null;
  }
}

function getPendingEventFromResponse(response: string): PendingCalendarEvent | null {
  const match = response.match(/__ALFRED_PENDING_EVENT__=(.+)$/m);
  if (!match) return null;

  try {
    return JSON.parse(match[1]) as PendingCalendarEvent;
  } catch {
    return null;
  }
}

function getVisibleResponse(response: string) {
  return response
    .replace(/\n?__ALFRED_CALENDAR_EVENT__=.+$/m, "")
    .replace(/\n?__ALFRED_PENDING_EVENT__=.+$/m, "")
    .trim();
}

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
  response = getVisibleResponse(response);

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
      .filter(
        (line) => line.startsWith("•") && line.includes(":") && !line.includes("—")
      )
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

function ProjectExplorer({
  data,
  onFolderClick,
  onOpenProject,
}: {
  data: ProjectExplorerData;
  onFolderClick: (path: string | null) => void;
  onOpenProject: (path: string) => void;
}) {
  return (
    <div className="project-explorer-card">
      <div className="project-explorer-header">
        <div>
          <p className="panel-label">project explorer</p>
          <h3>{data.current_path?.split(/[\\/]/).pop() || "src"}</h3>
          <small>{data.current_path}</small>
        </div>
        <FolderOpen size={20} />
      </div>

      {data.parent_path && (
        <button
          className="project-back-button"
          type="button"
          onClick={() => onFolderClick(data.parent_path || null)}
        >
          ← Back
        </button>
      )}

      <div className="project-file-list">
        {data.items.length === 0 ? (
          <small>No folders or files found.</small>
        ) : (
          data.items.map((item) => (
            <div className="project-file-row" key={item.path}>
              <button
                className="project-file-main"
                type="button"
                onClick={() => {
                  if (item.type === "folder") onFolderClick(item.path);
                }}
                disabled={item.type !== "folder"}
              >
                <FolderOpen size={16} />
                <span>{item.name}</span>
                <small>{item.type}</small>
              </button>

              {item.type === "folder" && (
                <button
                  className="project-open-button"
                  type="button"
                  onClick={() => onOpenProject(item.path)}
                >
                  Open in VS Code
                </button>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function App() {
  const [command, setCommand] = useState("");
  const [response, setResponse] = useState("Systems online. Awaiting command.");
  const [projectExplorer, setProjectExplorer] =
    useState<ProjectExplorerData | null>(null);

  const [calendarConnected, setCalendarConnected] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState("calendar not checked");
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [tomorrowPlan] = useState<TomorrowPlan | null>(null);

  const [eventTitle, setEventTitle] = useState("");
  const [eventDateTime, setEventDateTime] = useState("");
  const [eventLocation, setEventLocation] = useState("");
  const [eventDescription, setEventDescription] = useState("");
  const [eventStatus, setEventStatus] = useState("");
  const [eventDurationMinutes, setEventDurationMinutes] = useState(60);

  const [editableEvent, setEditableEvent] =
    useState<EditableCalendarEvent | null>(null);
  const [isEditingEvent, setIsEditingEvent] = useState(false);
  const [editEventTitle, setEditEventTitle] = useState("");
  const [editEventStart, setEditEventStart] = useState("");
  const [editEventEnd, setEditEventEnd] = useState("");
  const [editEventLocation, setEditEventLocation] = useState("");
  const [editEventDescription, setEditEventDescription] = useState("");
  const [editEventStatus, setEditEventStatus] = useState("");

  const [pendingEvent, setPendingEvent] = useState<PendingCalendarEvent | null>(null);
  const [pendingTitle, setPendingTitle] = useState("");
  const [pendingDate, setPendingDate] = useState("");
  const [pendingStartTime, setPendingStartTime] = useState("");
  const [pendingEndTime, setPendingEndTime] = useState("");
  const [pendingStatus, setPendingStatus] = useState("");
  
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

      if (!res.ok) {
        throw new Error(data.detail || "Command failed");
      }

      const responseText = data.response || "";
      const createdEvent = getCreatedEventFromResponse(responseText);
      const pending = getPendingEventFromResponse(responseText);

      setEditableEvent(createdEvent);
      setPendingEvent(pending);
      setIsEditingEvent(false);

      if (pending) {
        setPendingTitle(pending.draft.title || "");
        setPendingDate(pending.draft.date || "");
        setPendingStartTime(pending.draft.start_time || "");
        setPendingEndTime(pending.draft.end_time || "");
      }

      if (data.type === "project_list") {
        setProjectExplorer({
          success: data.success ?? true,
          message: data.message || data.response || "Showing projects.",
          root: data.root,
          current_path: data.current_path,
          parent_path: data.parent_path,
          items: data.items || [],
        });

        setResponse(getVisibleResponse(responseText) || data.message || "Project explorer loaded.");
      } else if (data.type === "project_explorer" && data.project_data) {
        setProjectExplorer(data.project_data);
        setResponse(getVisibleResponse(responseText) || "Project explorer loaded.");
      } else {
        setProjectExplorer(null);
        setResponse(getVisibleResponse(responseText));
      }

      setCommand("");
      loadUpcomingEvents();
    } catch {
      setResponse("Backend connection failed.");
    }
  }

  async function handlePendingEventSave(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!pendingEvent) return;

    const title = pendingTitle.trim();
    const date = pendingDate || pendingEvent.draft.date;
    const startTime = pendingStartTime || pendingEvent.draft.start_time;
    const endTime = pendingEndTime || pendingEvent.draft.end_time;

    if (!title || !date || !startTime) {
      setPendingStatus("Title, date, and start time are required.");
      return;
    }

    const start = new Date(`${date}T${startTime}`);
    const end = endTime
      ? new Date(`${date}T${endTime}`)
      : new Date(start.getTime() + 60 * 60 * 1000);

    if (end <= start) {
      end.setDate(end.getDate() + 1);
    }

    setPendingStatus("Creating event...");

    try {
      const created = await createCalendarEvent({
        title,
        start_time: start.toISOString(),
        end_time: end.toISOString(),
        location: pendingEvent.draft.location || "",
        description: pendingEvent.draft.description || "",
        reminder_minutes: 10,
      });

      const createdEvent = normalizeEditableEvent(created);

      if (!createdEvent) {
        setPendingStatus("Event was created, but ALFRED could not read the returned event data.");
        return;
      }

      setEditableEvent(createdEvent);
      setPendingEvent(null);
      setPendingStatus("");
      setResponse(`Created event: ${createdEvent.title}`);

      loadUpcomingEvents();
    } catch {
      setPendingStatus("Could not create event.");
    }
  }

  async function loadProjectFolder(path?: string | null) {
    const res = await fetch(`${API_BASE}/projects/list`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ path }),
    });

    const data = await res.json();
    setProjectExplorer(data);
    setResponse(data.message || "Project folder loaded.");
  }

  async function openProject(path: string) {
    const res = await fetch(`${API_BASE}/projects/open`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ path }),
    });

    const data = await res.json();
    setResponse(data.message || "Project opened.");
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

  async function handleCreateEvent(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!eventTitle.trim() || !eventDateTime) {
      setEventStatus("Add a title and date/time first.");
      return;
    }

    setEventStatus("Creating event...");

    try {
      const created = await createCalendarEventFromForm({
        title: eventTitle.trim(),
        dateTime: eventDateTime,
        location: eventLocation.trim(),
        description: eventDescription.trim(),
        durationMinutes: eventDurationMinutes,
        reminderMinutes: 10,
      });

      const createdStart = created.start;
      const createdEnd =
        created.end ||
        new Date(new Date(createdStart).getTime() + eventDurationMinutes * 60 * 1000).toISOString();

      const createdEvent: EditableCalendarEvent = {
        id: created.id,
        title: created.title,
        start: createdStart,
        end: createdEnd,
        location: created.location,
        description: created.description,
      };

      setEditableEvent(createdEvent);
      setIsEditingEvent(false);
      setEventStatus("Event created.");
      setResponse(
        `Created calendar event: ${createdEvent.title}\n` +
          `When: ${new Date(createdEvent.start).toLocaleString([], {
            weekday: "long",
            month: "long",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}\n` +
          `Ends: ${new Date(createdEvent.end).toLocaleString([], {
            weekday: "long",
            month: "long",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}\n` +
          `Location: ${createdEvent.location || "None"}`
      );

      setEventTitle("");
      setEventDateTime("");
      setEventLocation("");
      setEventDescription("");
      setEventDurationMinutes(60);

      loadUpcomingEvents();
    } catch {
      setEventStatus("Could not create event.");
    }
  }

  function openEventEditor(event: EditableCalendarEvent) {
    const normalizedEvent = normalizeEditableEvent(event);

    if (!normalizedEvent) {
      setEditEventStatus("Could not open editor because this event is missing start time data.");
      return;
    }

    const startDate = new Date(normalizedEvent.start);

    if (Number.isNaN(startDate.getTime())) {
      setEditEventStatus("Could not open editor because the start time is invalid.");
      return;
    }

    const fallbackEnd =
      normalizedEvent.end && !Number.isNaN(new Date(normalizedEvent.end).getTime())
        ? normalizedEvent.end
        : new Date(startDate.getTime() + 60 * 60 * 1000).toISOString();

    const eventWithEnd: EditableCalendarEvent = {
      ...normalizedEvent,
      end: fallbackEnd,
    };

    setEditableEvent(eventWithEnd);
    setEditEventTitle(eventWithEnd.title || "");
    setEditEventStart(toDateTimeLocalValue(eventWithEnd.start));
    setEditEventEnd(toDateTimeLocalValue(eventWithEnd.end));
    setEditEventLocation(eventWithEnd.location || "");
    setEditEventDescription(eventWithEnd.description || "");
    setEditEventStatus("");
    setIsEditingEvent(true);
  }

  function closeEventEditor() {
    setIsEditingEvent(false);
    setEditEventTitle("");
    setEditEventStart("");
    setEditEventEnd("");
    setEditEventLocation("");
    setEditEventDescription("");
    setEditEventStatus("");
  }

  async function handleUpdateEvent(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (!editableEvent) return;

    if (!editEventTitle.trim() || !editEventStart || !editEventEnd) {
      setEditEventStatus("Title, start, and end are required.");
      return;
    }

    const updatedStart = new Date(editEventStart);
    const updatedEnd = new Date(editEventEnd);

    if (updatedEnd <= updatedStart) {
      setEditEventStatus("End time must be after the start time.");
      return;
    }

    setEditEventStatus("Updating event...");

    try {
      const updated = await updateCalendarEvent(editableEvent.id, {
        title: editEventTitle.trim(),
        start_time: updatedStart.toISOString(),
        end_time: updatedEnd.toISOString(),
        location: editEventLocation.trim(),
        description: editEventDescription.trim(),
      });

      const normalizedUpdated = normalizeEditableEvent(updated);

      const updatedEvent: EditableCalendarEvent = normalizedUpdated || {
        id: editableEvent.id,
        title: editEventTitle.trim(),
        start: updatedStart.toISOString(),
        end: updatedEnd.toISOString(),
        location: editEventLocation.trim(),
        description: editEventDescription.trim(),
      };

      setEditableEvent(updatedEvent);
      setIsEditingEvent(false);
      setEditEventStatus("");

      setResponse(
        `Updated calendar event: ${updatedEvent.title}\n` +
          `When: ${new Date(updatedEvent.start).toLocaleString([], {
            weekday: "long",
            month: "long",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}\n` +
          `Ends: ${new Date(updatedEvent.end).toLocaleString([], {
            weekday: "long",
            month: "long",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
          })}\n` +
          `Location: ${updatedEvent.location || "None"}`
      );

      loadUpcomingEvents();
    } catch {
      setEditEventStatus("Could not update event.");
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
              Adaptive Learning Framework for Responsive Executive Decisions V.4
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
                placeholder='Try: "show me my projects"'
              />
              <button onClick={submitCommand} aria-label="Send command">
                <Send size={18} />
              </button>
            </div>
          </div>

          <div className="response-console">
            <p className="panel-label">system response</p>
            {projectExplorer ? (
              <ProjectExplorer
                data={projectExplorer}
                onFolderClick={loadProjectFolder}
                onOpenProject={openProject}
              />
            ) : (
              <>
                <ChatCalendarResponse response={response} />

                {pendingEvent && (
                  <form className="event-edit-panel" onSubmit={handlePendingEventSave}>
                    <div className="event-edit-header">
                      <div>
                        <p className="panel-label">missing event info</p>
                        <h3>Add missing fields</h3>
                      </div>
                    </div>

                    {pendingEvent.missing_fields.includes("title") && (
                      <label>
                        Title
                        <input
                          value={pendingTitle}
                          onChange={(e) => setPendingTitle(e.target.value)}
                          placeholder="Event title"
                        />
                      </label>
                    )}

                    {pendingEvent.missing_fields.includes("date") && (
                      <label>
                        Date
                        <input
                          type="date"
                          value={pendingDate}
                          onChange={(e) => setPendingDate(e.target.value)}
                        />
                      </label>
                    )}

                    {pendingEvent.missing_fields.includes("time") && (
                      <div className="event-edit-grid">
                        <label>
                          Start time
                          <input
                            type="time"
                            value={pendingStartTime}
                            onChange={(e) => setPendingStartTime(e.target.value)}
                          />
                        </label>

                        <label>
                          End time
                          <input
                            type="time"
                            value={pendingEndTime}
                            onChange={(e) => setPendingEndTime(e.target.value)}
                          />
                        </label>
                      </div>
                    )}

                    {pendingStatus && <small>{pendingStatus}</small>}

                    <div className="event-edit-actions">
                      <button type="submit" className="event-save-button">
                        Save event
                      </button>

                      <button
                        type="button"
                        className="event-cancel-button"
                        onClick={() => {
                          setPendingEvent(null);
                          setPendingStatus("");
                          setResponse("Event creation cancelled.");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
                {editableEvent && !isEditingEvent && (
                  <button
                    type="button"
                    className="event-edit-button"
                    onClick={() => openEventEditor(editableEvent)}
                  >
                    Edit event
                  </button>
                )}

                {isEditingEvent && editableEvent && (
                  <form className="event-edit-panel" onSubmit={handleUpdateEvent}>
                    <div className="event-edit-header">
                      <div>
                        <p className="panel-label">calendar edit</p>
                        <h3>Update Event</h3>
                      </div>
                    </div>

                    <label>
                      Title
                      <input
                        value={editEventTitle}
                        onChange={(e) => setEditEventTitle(e.target.value)}
                        placeholder="Event title"
                      />
                    </label>

                    <div className="event-edit-grid">
                      <label>
                        Start
                        <input
                          type="datetime-local"
                          value={editEventStart}
                          onChange={(e) => setEditEventStart(e.target.value)}
                        />
                      </label>

                      <label>
                        End
                        <input
                          type="datetime-local"
                          value={editEventEnd}
                          onChange={(e) => setEditEventEnd(e.target.value)}
                        />
                      </label>
                    </div>

                    <label>
                      Location
                      <input
                        value={editEventLocation}
                        onChange={(e) => setEditEventLocation(e.target.value)}
                        placeholder="Add a location"
                      />
                    </label>

                    <label>
                      Description
                      <textarea
                        value={editEventDescription}
                        onChange={(e) => setEditEventDescription(e.target.value)}
                        placeholder="Add a description"
                      />
                    </label>

                    {editEventStatus && <small>{editEventStatus}</small>}

                    <div className="event-edit-actions">
                      <button type="submit" className="event-save-button">
                        Save changes
                      </button>

                      <button
                        type="button"
                        className="event-cancel-button"
                        onClick={() => {
                          setIsEditingEvent(false);
                          setEditEventStatus("");
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </form>
                )}
              </>
            )}
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
        </aside>
      </section>
    </main>
  );
}

export default App;