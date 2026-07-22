import { type FormEvent, useEffect, useState } from "react";
import {
  Activity,
  CalendarDays,
  ChevronDown,
  Cpu,
  FileText,
  FolderOpen,
  Inbox,
  Loader2,
  Mail,
  MailCheck,
  MailOpen,
  Radio,
  Send,
  ShieldCheck,
  Terminal,
} from "lucide-react";

import {
  createCalendarEvent,
  updateCalendarEvent,
  deleteCalendarEvent,
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
  all_day?: boolean;
  location?: string | null;
  description?: string | null;
};

type EventOptionsPayload = {
  action: "update" | "delete";
  events: CalendarEvent[];
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

type SystemCheckItem = {
  label: string;
  status: "online" | "offline" | "checking";
  detail: string;
};

type EmailItem = {
  id?: string;
  thread_id?: string;
  from?: string;
  to?: string;
  cc?: string;
  subject?: string;
  date?: string;
  snippet?: string;
  body?: string;
  is_unread?: boolean;
};

type EmailDraft = {
  id?: string;
  draft_id?: string;
  message_id?: string;
  to?: string;
  subject?: string;
  body?: string;
};

type EmailResponseData = {
  type:
    | "email"
    | "email_list"
    | "email_summary"
    | "email_draft"
    | "email_sent"
    | "email_updated";

  overview: string;
  message: string;
  summary?: string;
  email?: EmailItem | null;
  emails?: EmailItem[];
  draft?: EmailDraft | null;
};

function getGreeting() {
  const hour = new Date().getHours();

  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

function getThinkingSteps(command: string) {
  const lower = command.toLowerCase();

  if (lower.includes("calendar") || lower.includes("event")) {
    return [
      "Reading your calendar request",
      "Checking calendar tools",
      "Preparing the response",
    ];
  }

  if (
    lower.includes("email") ||
    lower.includes("inbox") ||
    lower.includes("gmail")
  ) {
    if (
      lower.includes("draft") ||
      lower.includes("compose") ||
      lower.includes("write")
    ) {
      return [
        "Reading the email details",
        "Creating the Gmail draft",
        "Preparing the draft preview",
      ];
    }

    if (lower.includes("send")) {
      return [
        "Checking the recipient and message",
        "Sending through Gmail",
        "Confirming delivery",
      ];
    }

    if (lower.includes("summarize")) {
      return [
        "Checking your inbox",
        "Reviewing email previews",
        "Preparing your briefing",
      ];
    }

    return [
      "Reading your email request",
      "Checking Gmail",
      "Preparing the results",
    ];
  }

  if (lower.includes("project") || lower.includes("folder")) {
    return [
      "Finding the right project command",
      "Checking local project access",
      "Loading results",
    ];
  }

  return [
    "Reading your request",
    "Choosing the right tool",
    "Preparing the response",
  ];
}

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

function getEventOptionsFromResponse(response: string): EventOptionsPayload | null {
  const match = response.match(/__ALFRED_EVENT_OPTIONS__=(.+)$/m);
  if (!match) return null;

  try {
    return JSON.parse(match[1]) as EventOptionsPayload;
  } catch {
    return null;
  }
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
    .replace(/\n?__ALFRED_EVENT_OPTIONS__=.+$/m, "")
    .trim();
}

function isDateOnly(value?: string | null) {
  return !!value && /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function parseLocalCalendarDate(value?: string | null) {
  if (!value) return null;

  if (isDateOnly(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day, 12, 0, 0);
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatUpcomingWeekday(event: CalendarEvent) {
  const date = parseLocalCalendarDate(event.start);
  if (!date) return "";

  return date.toLocaleDateString([], { weekday: "short" });
}

function formatUpcomingTime(event: CalendarEvent) {
  if (event.all_day || isDateOnly(event.start)) return "All day";

  const date = parseLocalCalendarDate(event.start);
  if (!date) return "";

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatUpcomingDate(event: CalendarEvent) {
  const date = parseLocalCalendarDate(event.start);
  if (!date) return "";

  return date.toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function toLocalApiDateTime(value: string) {
  return value;
}

function splitWeeklyCalendarResponse(response: string) {
  const weeklyStartIndex = response.indexOf("Weekly Calendar Overview");

  if (weeklyStartIndex === -1) {
    return {
      quickSummary: "",
      calendarResponse: response,
    };
  }

  return {
    quickSummary: response.slice(0, weeklyStartIndex).trim(),
    calendarResponse: response.slice(weeklyStartIndex).trim(),
  };
}

function getCalendarLabelFromTitle(title: string) {
  return title
    .replace(/^Here’s your calendar for\s+/i, "")
    .replace(/^No events\s+/i, "")
    .replace(/^You have nothing on your calendar\s*/i, "")
    .replace(/[.:]+$/g, "")
    .trim();
}

function buildDailyCalendarQuickSummary(calendarResponse: string) {
  const parsed = parseCalendarResponse(calendarResponse);

  if (!parsed || parsed.type !== "daily") return "";

  const dayLabel = getCalendarLabelFromTitle(parsed.title) || "that day";

  if (parsed.events.length === 0) {
    return `Absolutely, here’s your calendar ${dayLabel}. Looks clear, you have no events ${dayLabel}.`;
  }

  const eventTitles = parsed.events.map((event) => event.title).join(", ");

  return `Absolutely, here’s your calendar ${dayLabel}. Looks like you have ${parsed.events.length} ${
    parsed.events.length === 1 ? "event" : "events"
  }: ${eventTitles}.`;
}

function splitCalendarResponse(response: string) {
  const parsed = parseCalendarResponse(response);

  if (response.includes("Weekly Calendar Overview")) {
    const { quickSummary, calendarResponse } =
      splitWeeklyCalendarResponse(response);

    return {
      quickSummary:
        quickSummary ||
        "Absolutely, here’s your calendar for the week. I pulled everything into a weekly overview for you.",
      calendarResponse,
    };
  }

  if (parsed?.type === "daily") {
    return {
      quickSummary: buildDailyCalendarQuickSummary(response),
      calendarResponse: response,
    };
  }

  return {
    quickSummary: "",
    calendarResponse: "",
  };
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

  const isWeeklyCalendar = response.includes("Weekly Calendar Overview");

  if (!isDailyCalendar && !isWeeklyCalendar) return null;

  if (isWeeklyCalendar) {
    const weeklyStartIndex = response.indexOf("Weekly Calendar Overview");
    const quickSummary = response.slice(0, weeklyStartIndex).trim();
    const weeklyResponse = response.slice(weeklyStartIndex);
    const lines = weeklyResponse.split("\n");
    
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
      quickSummary,
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

function parseWeatherResponse(response: string) {
  response = getVisibleResponse(response);

  const weeklyMatch = response.match(/^Weather this week for (.+):\n([\s\S]+)/);
  if (weeklyMatch) {
    const location = weeklyMatch[1];

    type WeatherDay = {
      date: string;
      high: string;
      low: string;
      rain: string;
    };

    const days = weeklyMatch[2]
      .split("\n")
      .map((line): WeatherDay | null => {
        const match = line.match(
          /^-\s*(\d{4}-\d{2}-\d{2}):\s*High\s*(.+?)°F,\s*low\s*(.+?)°F,\s*rain chance\s*(.+?)%/i
        );

        if (!match) return null;

        return {
          date: match[1],
          high: match[2],
          low: match[3],
          rain: match[4],
        };
      })
      .filter((day): day is WeatherDay => day !== null)
      .sort((a, b) => {
        const dayA = new Date(`${a.date}T12:00:00`).getDay();
        const dayB = new Date(`${b.date}T12:00:00`).getDay();

        return dayA - dayB;
      });

    return { type: "weekly" as const, location, days };
  }

  const todayMatch = response.match(
    /^Weather for (.+?): currently (.+?)°F with (.+?)% humidity\. Today's high is (.+?)°F and the low is (.+?)°F\. Chance of rain is up to (.+?)%\./
  );

  if (todayMatch) {
    return {
      type: "single" as const,
      title: `Weather for ${todayMatch[1]}`,
      stats: [
        { label: "Current", value: `${todayMatch[2]}°F` },
        { label: "Humidity", value: `${todayMatch[3]}%` },
        { label: "High", value: `${todayMatch[4]}°F` },
        { label: "Low", value: `${todayMatch[5]}°F` },
        { label: "Rain", value: `${todayMatch[6]}%` },
      ],
    };
  }

  const tomorrowMatch = response.match(
    /^Tomorrow in (.+?): high of (.+?)°F, low of (.+?)°F, with up to a (.+?)% chance of rain\./
  );

  if (tomorrowMatch) {
    return {
      type: "single" as const,
      title: `Tomorrow in ${tomorrowMatch[1]}`,
      stats: [
        { label: "High", value: `${tomorrowMatch[2]}°F` },
        { label: "Low", value: `${tomorrowMatch[3]}°F` },
        { label: "Rain", value: `${tomorrowMatch[4]}%` },
      ],
    };
  }

  const simpleMatch = response.match(/^(The .+? in .+? is|The chance of rain tomorrow in .+? is up to) (.+?)(\.?)$/);

  if (simpleMatch) {
    return {
      type: "single" as const,
      title: "Weather Update",
      stats: [{ label: "Result", value: simpleMatch[2] }],
      note: response,
    };
  }

  return null;
}

function ChatWeatherResponse({ response }: { response: string }) {
  const parsed = parseWeatherResponse(response);

  if (!parsed) return null;

  if (parsed.type === "weekly") {
    return (
      <div className="chat-weather-card">
        <div className="chat-weather-header centered">
          <div>
            <h3>{parsed.location}</h3>
          </div>
        </div>

        <div className="chat-weather-week-grid">
          {parsed.days.map((day) => {
            const parsedDate = new Date(`${day.date}T12:00:00`);

            return (
              <div className="chat-weather-day" key={day.date}>
                <span>
                  {parsedDate.toLocaleDateString([], {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                  })}
                </span>

                <div className="chat-weather-temp-row">
                  <strong>{day.high}°</strong>
                  <small>{day.low}°</small>
                </div>

                <small>Rain {day.rain}%</small>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="chat-weather-card">
      <div className="chat-weather-header centered">
        <div>
          <h3>{parsed.title}</h3>
        </div>
      </div>

      <div className="chat-weather-stat-grid">
        {parsed.stats.map((stat) => (
          <div className="chat-weather-stat" key={stat.label}>
            <span>{stat.label}</span>
            <strong>{stat.value}</strong>
          </div>
        ))}
      </div>

      {"note" in parsed && parsed.note && (
        <small className="chat-weather-note">{parsed.note}</small>
      )}
    </div>
  );
}

function EmailStatusBadge({ unread }: { unread?: boolean }) {
  return (
    <span className={`email-status-badge ${unread ? "unread" : "read"}`}>
      {unread ? (
        <>
          <Mail size={13} />
          Unread
        </>
      ) : (
        <>
          <MailOpen size={13} />
          Read
        </>
      )}
    </span>
  );
}

function EmailMessageCard({
  email,
  expanded = false,
}: {
  email: EmailItem;
  expanded?: boolean;
}) {
  const body =
    email.body ||
    email.snippet ||
    "This email does not contain a readable preview.";

  return (
    <article className={`email-message-card ${email.is_unread ? "unread" : ""}`}>
      <div className="email-message-top">
        <div className="email-sender-icon">
          {email.is_unread ? <Mail size={18} /> : <MailOpen size={18} />}
        </div>

        <div className="email-message-heading">
          <strong>{email.subject || "(No subject)"}</strong>
          <span>{email.from || "Unknown sender"}</span>
        </div>

        <EmailStatusBadge unread={email.is_unread} />
      </div>

      <div className="email-message-meta">
        {email.to && (
          <span>
            <strong>To</strong>
            {email.to}
          </span>
        )}

        {email.date && (
          <span>
            <strong>Date</strong>
            {email.date}
          </span>
        )}
      </div>

      <div className={`email-message-body ${expanded ? "expanded" : ""}`}>
        {body}
      </div>
    </article>
  );
}

type EmailBriefingSection = {
  title: string;
  items: string[];
};

type ParsedEmailBriefing = {
  title: string;
  sections: EmailBriefingSection[];
};

function cleanBriefingLine(value: string) {
  return value
    .replace(/^\*\*/, "")
    .replace(/\*\*:?\s*$/, "")
    .replace(/^#+\s*/, "")
    .trim();
}

function parseEmailBriefing(
  summary: string
): ParsedEmailBriefing {
  const lines = summary
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  let title = "Inbox Briefing";
  const sections: EmailBriefingSection[] = [];
  let currentSection: EmailBriefingSection | null = null;

  lines.forEach((line, index) => {
    const isMarkdownHeading =
      /^\*\*.+?\*\*:?\s*$/.test(line);

    const isPlainHeading =
      /^(Inbox Briefing|Overview|Important\/Missing Actions|Visible Deadlines\/Meetings\/Payments|Replies Needed|FYI Section):?$/i.test(
        cleanBriefingLine(line)
      );

    if (
      index === 0 &&
      cleanBriefingLine(line).toLowerCase() ===
        "inbox briefing"
    ) {
      title = "Inbox Briefing";
      return;
    }

    if (isMarkdownHeading || isPlainHeading) {
      const sectionTitle = cleanBriefingLine(line);

      if (
        sectionTitle.toLowerCase() ===
        "inbox briefing"
      ) {
        title = sectionTitle;
        return;
      }

      currentSection = {
        title: sectionTitle.replace(/:$/, ""),
        items: [],
      };

      sections.push(currentSection);
      return;
    }

    const cleanedItem = line
      .replace(/^[-•]\s*/, "")
      .replace(/^\d+\.\s*/, "")
      .trim();

    if (!cleanedItem) return;

    if (!currentSection) {
      currentSection = {
        title: "Overview",
        items: [],
      };

      sections.push(currentSection);
    }

    currentSection.items.push(cleanedItem);
  });

  return {
    title,
    sections,
  };
}

function EmailBriefing({
  summary,
}: {
  summary: string;
}) {
  const {
    displayedText,
    isTyping,
  } = useTypewriter(summary, true, 15);

  const parsed = parseEmailBriefing(displayedText);

  function getSectionClass(title: string) {
    const normalized = title.toLowerCase();

    if (
      normalized.includes("important") ||
      normalized.includes("action")
    ) {
      return "actions";
    }

    if (
      normalized.includes("deadline") ||
      normalized.includes("meeting") ||
      normalized.includes("payment")
    ) {
      return "deadlines";
    }

    if (normalized.includes("replies")) {
      return "replies";
    }

    if (normalized.includes("fyi")) {
      return "fyi";
    }

    return "overview";
  }

  return (
    <section
      className={`email-briefing ${
        isTyping ? "typing" : "complete"
      }`}
    >
      <div className="email-briefing-header">
        <div>
          <p className="panel-label">
            intelligence summary
          </p>
          <h3>{parsed.title}</h3>
        </div>

        <span className="email-briefing-status">
          {isTyping ? "Analyzing" : "Complete"}
        </span>
      </div>

      <div className="email-briefing-sections">
        {parsed.sections.map((section, index) => (
          <div
            className={`email-briefing-section ${getSectionClass(
              section.title
            )}`}
            key={`${section.title}-${index}`}
          >
            <div className="email-briefing-section-heading">
              <span className="email-briefing-index">
                {String(index + 1).padStart(2, "0")}
              </span>

              <strong>{section.title}</strong>
            </div>

            <div className="email-briefing-items">
              {section.items.map((item, itemIndex) => (
                <div
                  className="email-briefing-item"
                  key={`${item}-${itemIndex}`}
                >
                  <span />
                  <p>{item}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ChatEmailResponse({
  data,
}: {
  data: EmailResponseData;
}) {
  const emails = data.emails || [];
  const isSingleEmail = Boolean(data.email);
  const isSummary = data.type === "email_summary";
  const isDraft = data.type === "email_draft";
  const isSent = data.type === "email_sent";

  if (isDraft) {
    return (
      <div className="chat-email-card">
        <div className="chat-email-header">
          <div className="chat-email-header-icon">
            <FileText size={19} />
          </div>

          <div>
            <p className="panel-label">email draft</p>
            <h3>Draft Created</h3>
          </div>
        </div>

        <div className="email-action-banner success">
          <MailCheck size={17} />
          <span>{data.message}</span>
        </div>

        {data.draft && (
          <div className="email-draft-preview">
            <div className="email-draft-field">
              <span>To</span>
              <strong>{data.draft.to || "Recipient saved in Gmail"}</strong>
            </div>

            <div className="email-draft-field">
              <span>Subject</span>
              <strong>{data.draft.subject || "(No subject)"}</strong>
            </div>

            {data.draft.body && (
              <div className="email-draft-body">
                {data.draft.body}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  if (isSent) {
    return (
      <div className="chat-email-card">
        <div className="chat-email-header">
          <div className="chat-email-header-icon">
            <Send size={19} />
          </div>

          <div>
            <p className="panel-label">email action</p>
            <h3>Email Sent</h3>
          </div>
        </div>

        <div className="email-action-banner success">
          <MailCheck size={17} />
          <span>{data.message}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-email-card">
      <div className="chat-email-header">
        <div className="chat-email-header-icon">
          {isSummary ? (
            <FileText size={19} />
          ) : (
            <Inbox size={19} />
          )}
        </div>

        <div>
          <p className="panel-label">
            {isSummary
              ? "email intelligence"
              : "gmail response"}
          </p>

          <h3>
            {isSummary
              ? "Inbox Analysis"
              : isSingleEmail
                ? "Email Message"
                : `${emails.length} ${
                    emails.length === 1
                      ? "Email"
                      : "Emails"
                  }`}
          </h3>
        </div>
      </div>

      {isSummary && data.summary && (
        <EmailBriefing summary={data.summary} />
      )}

      {data.email && (
        <div className="email-message-list">
          <EmailMessageCard
            email={data.email}
            expanded
          />
        </div>
      )}

      {!data.email && emails.length > 0 && (
        <>
          {isSummary && (
            <div className="email-source-divider">
              <span>Source Emails</span>
            </div>
          )}

          <div className="email-message-list">
            {emails.map((email, index) => (
              <EmailMessageCard
                email={email}
                key={
                  email.id ||
                  `${email.subject}-${index}`
                }
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function useTypewriter(
  text: string,
  enabled: boolean,
  speed = 18
) {
  const [displayedText, setDisplayedText] =
    useState(enabled ? "" : text);

  const [isTyping, setIsTyping] =
    useState(enabled && text.length > 0);

  useEffect(() => {
    if (!enabled) {
      setDisplayedText(text);
      setIsTyping(false);
      return;
    }

    if (!text) {
      setDisplayedText("");
      setIsTyping(false);
      return;
    }

    setDisplayedText("");
    setIsTyping(true);

    let index = 0;

    const timer = window.setInterval(() => {
      index += 1;
      setDisplayedText(text.slice(0, index));

      if (index >= text.length) {
        window.clearInterval(timer);
        setDisplayedText(text);
        setIsTyping(false);
      }
    }, speed);

    return () => {
      window.clearInterval(timer);
    };
  }, [text, enabled, speed]);

  return {
    displayedText,
    isTyping,
  };
}

function ChatCalendarResponse({ response }: { response: string }) {
  const parsed = parseCalendarResponse(response);
  const [openDayIndex, setOpenDayIndex] = useState<number | null>(null);

  if (!parsed) {
    const weatherParsed = parseWeatherResponse(response);

    if (weatherParsed) {
      return <ChatWeatherResponse response={response} />;
    }

    return <p>{response}</p>;
  }

  if (parsed.type === "weekly") {
    return (
      <div className="chat-calendar-card">
        {parsed.quickSummary && (
          <div className="chat-week-summary">
            <span>Quick Summary</span>
            <small>{parsed.quickSummary}</small>
          </div>
        )}
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

function ProcessingPanel({ steps }: { steps: string[] }) {
  return (
    <div className="processing-panel">
      <div className="processing-header">
        <Loader2 size={18} />
        <span>ALFRED is thinking</span>
        <span className="processing-dots">
          <i />
          <i />
          <i />
        </span>
      </div>

      <div className="processing-steps">
        {steps.map((step, index) => (
          <div className="processing-step" key={step}>
            <span>{index + 1}</span>
            <small>{step}</small>
          </div>
        ))}
      </div>
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

function normalizeProjectItems(items: any[]): ProjectItem[] {
  if (!Array.isArray(items)) return [];

  return items.map((item) => {
    if (typeof item === "string") {
      return {
        name: item.split(/[\\/]/).pop() || item,
        path: item,
        type: "folder",
        can_open: true,
      };
    }

    return {
      name: item.name || item.title || item.path?.split(/[\\/]/).pop() || "Untitled",
      path: item.path || item.full_path || item.name || "",
      type: item.type === "file" ? "file" : "folder",
      can_open: item.can_open ?? true,
    };
  });
}

function pluralize(
  count: number,
  singular: string,
  plural = `${singular}s`
) {
  return count === 1 ? singular : plural;
}

function buildAlfredOverview(
  data: any,
  command: string
): string {
  const lower = command.toLowerCase();

  if (data.type === "email_summary") {
    const count = Array.isArray(data.emails)
      ? data.emails.length
      : 0;

    if (count === 0) {
      return "Absolutely. I checked your inbox, but I couldn’t find any emails matching that request.";
    }

    return (
      `Absolutely, here’s a briefing on your ${count} latest ` +
      `${pluralize(count, "email")}.`
    );
  }

  if (data.type === "email_list") {
    const count = Array.isArray(data.emails)
      ? data.emails.length
      : 0;

    if (count === 0) {
      return "Absolutely. I checked your inbox, but I couldn’t find any matching emails.";
    }

    const unreadText = lower.includes("unread")
      ? " unread"
      : "";

    return (
      `Absolutely, here ${count === 1 ? "is" : "are"} your ` +
      `${count} latest${unreadText} ${pluralize(count, "email")}.`
    );
  }

  if (data.type === "email") {
    const subject = data.email?.subject;

    return subject
      ? `Absolutely, here’s the email titled “${subject}.”`
      : "Absolutely, here’s the email you asked me to read.";
  }

  if (data.type === "email_draft") {
    const recipient = data.draft?.to;

    return recipient
      ? `Absolutely, I created an email draft for ${recipient}.`
      : "Absolutely, I created that email draft for you.";
  }

  if (data.type === "email_sent") {
    const recipient =
      data.email?.to ||
      data.sent_email?.to;

    return recipient
      ? `Absolutely, I sent your email to ${recipient}.`
      : "Absolutely, your email has been sent.";
  }

  if (
    data.type === "project_list" ||
    data.type === "projects" ||
    data.type === "project_explorer"
  ) {
    return (
      data.message ||
      "Absolutely, I found your project files and loaded them below."
    );
  }

  if (data.type === "weather") {
    return "Absolutely, here’s the weather information you asked for.";
  }

  return "";
}

function App() {
  const [command, setCommand] = useState("");
  const startupMessage = `${getGreeting()}, Kaylee. Running systems check...`;
  const [response, setResponse] = useState(startupMessage);
  const [displayedResponse, setDisplayedResponse] = useState(startupMessage);
  const [isTypingResponse, setIsTypingResponse] = useState(false);
  const [shouldTypeResponse, setShouldTypeResponse] = useState(false);
  const [projectExplorer, setProjectExplorer] =
    useState<ProjectExplorerData | null>(null);

  const [emailResponse, setEmailResponse] =
    useState<EmailResponseData | null>(null);
  const [calendarCardResponse, setCalendarCardResponse] = useState("");
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [calendarStatus, setCalendarStatus] = useState("calendar not checked");
  const [events, setEvents] = useState<CalendarEvent[]>([]);

  const [eventOptions, setEventOptions] = useState<EventOptionsPayload | null>(null);

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
  
  const [showStartupChecks, setShowStartupChecks] = useState(true);
  const [, setBackendOnline] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [thinkingSteps, setThinkingSteps] = useState<string[]>([]);
  const [systemChecks, setSystemChecks] = useState<SystemCheckItem[]>([
    {
      label: "Backend",
      status: "checking",
      detail: "Checking local FastAPI service",
    },
    {
      label: "Calendar API",
      status: "checking",
      detail: "Checking Google Calendar sync",
    },
    {
      label: "Project tools",
      status: "checking",
      detail: "Waiting for backend confirmation",
    },
  ]);

  async function submitCommand() {
    const trimmedCommand = command.trim();
    if (!trimmedCommand) return;
    setShowStartupChecks(false);

    setIsProcessing(true);
    setThinkingSteps(getThinkingSteps(trimmedCommand));
    setResponse("");
    setDisplayedResponse("");
    setShouldTypeResponse(false);
    setCalendarCardResponse("");
    setEmailResponse(null);
    setEventOptions(null);

    const controller = new AbortController();

    const COMMAND_TIMEOUT_MS = 65_000;

    const timeoutId = window.setTimeout(() => {
      controller.abort();
    }, COMMAND_TIMEOUT_MS);

    try {
      const res = await fetch(`${API_BASE}/command`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ command: trimmedCommand }),
        signal: controller.signal,
      });

      window.clearTimeout(timeoutId);

      let data: any;

      try {
        data = await res.json();
      } catch {
        throw new Error("The backend returned something ALFRED could not read.");
      }

      if (!res.ok) {
        throw new Error(data.detail || data.response || "Command failed.");
      }

      const responseText = data.response || "";
      const visibleResponse = getVisibleResponse(responseText);

      const createdEvent = getCreatedEventFromResponse(responseText);
      const pending = getPendingEventFromResponse(responseText);
      const eventOptionsPayload = getEventOptionsFromResponse(responseText);

      setEditableEvent(createdEvent);
      setPendingEvent(pending);
      setEventOptions(eventOptionsPayload);
      setIsEditingEvent(false);

      if (pending) {
        setPendingTitle(pending.draft.title || "");
        setPendingDate(pending.draft.date || "");
        setPendingStartTime(pending.draft.start_time || "");
        setPendingEndTime(pending.draft.end_time || "");
      }

      if (data.type === "project_list" || data.type === "projects") {
        const rawItems = data.items || data.projects || [];

        setProjectExplorer({
          success: data.success ?? true,
          message: data.message || data.response || "Showing projects.",
          root: data.root || data.current_path || "C:\\Users\\alpha\\src",
          current_path: data.current_path || data.root || "C:\\Users\\alpha\\src",
          parent_path: data.parent_path || null,
          items: normalizeProjectItems(rawItems),
        });

        const overview =
          data.message ||
          "Absolutely, I found your projects and loaded them below.";

        setResponse(
          overview ||
            visibleResponse ||
            data.message ||
            data.response ||
            "Project explorer loaded."
        );
        setShouldTypeResponse(true);
      } else if (data.type === "project_explorer" && data.project_data) {
        setProjectExplorer({
          ...data.project_data,
          items: normalizeProjectItems(data.project_data.items || []),
        });

        const overview =
          data.message ||
          visibleResponse ||
          "Absolutely, I loaded that project folder for you.";

        setResponse(overview);
        setShouldTypeResponse(true);
      } else if (
        [
          "email",
          "email_list",
          "email_summary",
          "email_draft",
          "email_sent",
          "email_updated",
        ].includes(data.type)
      ) {
        setProjectExplorer(null);
        setCalendarCardResponse("");

        const overview = buildAlfredOverview(
          data,
          trimmedCommand
        );

        setEmailResponse({
          type: data.type,
          overview,
          message: data.response || overview,
          summary: data.summary || "",
          email: data.email || null,
          emails: data.emails || [],
          draft: data.draft || null,
        });

        setResponse(overview);
        setShouldTypeResponse(true);
      } else {
        setProjectExplorer(null);

        const finalResponse = visibleResponse || data.response || "";

        const splitCalendar = splitCalendarResponse(finalResponse);

        if (splitCalendar.calendarResponse) {
          setCalendarCardResponse(splitCalendar.calendarResponse);
          setShouldTypeResponse(true);
          setResponse(splitCalendar.quickSummary);
        } else {
          setCalendarCardResponse("");
          setShouldTypeResponse(true);
          setResponse(finalResponse);
        }
      }

      setCommand("");
      await loadUpcomingEvents();
    } catch (error: any) {
      console.error(error);
      window.clearTimeout(timeoutId);

      let message = "Something went wrong, but ALFRED is still running.";

      if (error?.name === "AbortError") {
        message =
          "That request took longer than expected. ALFRED is still running. " +
          "Try requesting fewer emails, such as your five newest unread messages.";
      } else if (error?.message?.includes("Failed to fetch")) {
        message = "I couldn’t reach the backend. Make sure the FastAPI server is running.";
      } else if (error?.message) {
        message = error.message;
      }

      setProjectExplorer(null);
        setCalendarCardResponse("");
      setEmailResponse(null);
      setEventOptions(null);
      setPendingEvent(null);
      setEditableEvent(null);
      setIsEditingEvent(false);

      setShouldTypeResponse(true);
      setResponse(message);
    } finally {
      setIsProcessing(false);
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
        start_time: `${date}T${startTime}`,
        end_time: endTime ? `${date}T${endTime}` : `${date}T${pendingEndTime || "23:59"}`,
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
      setShouldTypeResponse(true);
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
    setShouldTypeResponse(true);
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
    setShouldTypeResponse(true);
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

  async function runSystemCheck() {
    const checks: SystemCheckItem[] = [];

    let backendOk = false;

    try {
      const res = await fetch(`${API_BASE}/`);
      backendOk = res.ok;

      checks.push({
        label: "Backend",
        status: backendOk ? "online" : "offline",
        detail: backendOk ? "FastAPI backend responded" : "Backend did not respond cleanly",
      });
    } catch {
      checks.push({
        label: "Backend",
        status: "offline",
        detail: "Could not reach FastAPI backend",
      });
    }

    setBackendOnline(backendOk);

    try {
      const res = await fetch(`${API_BASE}/calendar/upcoming?days=7&max_results=5`);
      const data = await res.json();

      if (!res.ok) throw new Error(data.detail || "Calendar unavailable");

      setEvents(data.events || []);
      setCalendarConnected(true);
      setCalendarStatus("calendar synced");

      checks.push({
        label: "Calendar API",
        status: "online",
        detail: "Calendar connected and upcoming events loaded",
      });
    } catch {
      setCalendarConnected(false);
      setCalendarStatus("calendar offline");

      checks.push({
        label: "Calendar API",
        status: "offline",
        detail: "Calendar is not connected or needs re-auth",
      });
    }

    checks.push({
      label: "Project tools",
      status: backendOk ? "online" : "offline",
      detail: backendOk
        ? "Project launcher ready through backend"
        : "Project tools unavailable until backend is online",
    });

    setSystemChecks(checks);

    const allOnline = checks.every((check) => check.status === "online");
    const partiallyOnline = checks.some((check) => check.status === "online");

    setShouldTypeResponse(true);
    setResponse(
      `${getGreeting()}, Kaylee.\n\n` +
        `${allOnline || partiallyOnline ? "Ready when you are." : "Some systems are offline. Start the backend, then refresh ALFRED."}`
    );
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
        start_time: toLocalApiDateTime(editEventStart),
        end_time: toLocalApiDateTime(editEventEnd),
        location: editEventLocation.trim(),
        description: editEventDescription.trim(),
      });

      const normalizedUpdated = normalizeEditableEvent(updated);

      const updatedEvent: EditableCalendarEvent = normalizedUpdated || {
        id: editableEvent.id,
        title: editEventTitle.trim(),
        start: editEventStart,
        end: editEventEnd,
        location: editEventLocation.trim(),
        description: editEventDescription.trim(),
      };

      setEditableEvent(updatedEvent);
      setIsEditingEvent(false);
      setEditEventStatus("");

      setShouldTypeResponse(true);
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

  async function handleDeleteEvent(event: CalendarEvent) {
    if (!event.id) return;

    const confirmed = window.confirm(`Delete "${event.title}"?`);
    if (!confirmed) return;

    try {
      await deleteCalendarEvent(event.id);

      setShouldTypeResponse(true);
      setResponse(`Deleted calendar event: ${event.title}`);
      setEditableEvent(null);
      setIsEditingEvent(false);

      await loadUpcomingEvents();
    } catch {
      setShouldTypeResponse(true);
      setResponse("Could not delete event.");
    }
  }

  async function handleOptionDelete(event: CalendarEvent) {
    if (!event.id) return;

    try {
      await deleteCalendarEvent(event.id);
      setEventOptions(null);
      setResponse(`Deleted event: ${event.title}`);
      await loadUpcomingEvents();
    } catch {
      setShouldTypeResponse(true);
      setResponse("Could not delete event.");
    }
  }

  function handleOptionUpdate(event: CalendarEvent) {
    const editable = normalizeEditableEvent(event);
    if (!editable) {
      setShouldTypeResponse(true);
      setResponse("Could not open that event for editing.");
      return;
    }

    setEventOptions(null);
    openEventEditor(editable);
  }

  useEffect(() => {
    runSystemCheck();
  }, []);

  useEffect(() => {
    if (!shouldTypeResponse) {
      setDisplayedResponse(response);
      setIsTypingResponse(false);
      return;
    }

    if (!response) {
      setDisplayedResponse("");
      setIsTypingResponse(false);
      return;
    }

    setDisplayedResponse("");
    setIsTypingResponse(true);

    let index = 0;

    const timer = window.setInterval(() => {
      index += 1;
      setDisplayedResponse(response.slice(0, index));

      if (index >= response.length) {
        window.clearInterval(timer);
        setDisplayedResponse(response);
        setIsTypingResponse(false);
      }
    }, 32);

    return () => {
      window.clearInterval(timer);
    };
  }, [response, shouldTypeResponse]);

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
                  ? "calendar online"
                  : "agent idle · monitoring input"}
              </span>
            </div>
          </div>
        </aside>

        <section className="center-console">
           <div className="title-group">
            <h1>A.L.F.R.E.D.</h1>
            <p className="subtitle">
              Adaptive Learning Framework for Responsive Executive Decisions V.7
            </p>
          </div>

          <div className="command-console">
            <div className="console-header">
              <Terminal size={18} />
              <span>command input</span>
            </div>

            <div className="command-input-row">
              <textarea
                className="command-textarea"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submitCommand();
                  }
                }}
                rows={1}
                placeholder='Try: "show me my projects"'
              />
              <button onClick={submitCommand} aria-label="Send command">
                <Send size={18} />
              </button>
            </div>
          </div>

          <div className="response-console">
            <p className="panel-label">system response</p>
            {showStartupChecks && !isProcessing && !projectExplorer && (
              <div className="system-check-grid">
                {systemChecks.map((check) => (
                  <div
                    className={`system-check-card ${check.status}`}
                    key={check.label}
                  >
                    <span>{check.label}</span>
                    <small>{check.detail}</small>
                  </div>
                ))}
              </div>
            )}
            {isProcessing ? (
              <ProcessingPanel steps={thinkingSteps} />
            ) : projectExplorer ? (
              <div className="structured-response-stack">
                <p className="alfred-response-overview">
                  {displayedResponse}
                </p>

                {!isTypingResponse && (
                  <ProjectExplorer
                    data={projectExplorer}
                    onFolderClick={loadProjectFolder}
                    onOpenProject={openProject}
                  />
                )}
              </div>
            ) : emailResponse ? (
              <div className="structured-response-stack">
                <p className="alfred-response-overview">
                  {displayedResponse}
                </p>

                {!isTypingResponse && (
                  <ChatEmailResponse data={emailResponse} />
                )}
              </div>
            ) : (
              <>
                <div className="typewriter-response">
                  {calendarCardResponse ? (
                    <>
                      <p className="calendar-quick-text">{displayedResponse}</p>

                      {!isTypingResponse && (
                        <ChatCalendarResponse response={calendarCardResponse} />
                      )}
                    </>
                  ) : (
                    <ChatCalendarResponse
                      response={(shouldTypeResponse ? displayedResponse : response) || "Ready when you are."}
                    />
                  )}
                </div>
                
                {eventOptions && (
                  <div className="event-options-panel">
                    <p className="panel-label">
                      {eventOptions.action === "delete" ? "delete options" : "update options"}
                    </p>

                    {eventOptions.events.map((event) => (
                      <div className="event-option-row" key={event.id}>
                        <div className="event-option-details">
                          <strong>{event.title}</strong>
                          <small>
                            {new Date(event.start).toLocaleString([], {
                              weekday: "short",
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </small>
                          {event.location && <small>{event.location}</small>}
                        </div>

                        {eventOptions.action === "delete" ? (
                          <button type="button" onClick={() => handleOptionDelete(event)}>
                            Delete
                          </button>
                        ) : (
                          <button type="button" onClick={() => handleOptionUpdate(event)}>
                            Update
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}

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
                          setShouldTypeResponse(true);
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

                      <button
                        type="button"
                        className="event-delete-button event-delete-edit-button"
                        onClick={() => handleDeleteEvent(editableEvent)}
                      >
                        Delete event
                      </button>
                    </div>
                  </form>
                )}
              </>
            )}
          </div>
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
                    <button
                      type="button"
                      className="event-item-main"
                      onClick={() => {
                        const editable = normalizeEditableEvent(event);
                        if (editable) openEventEditor(editable);
                      }}
                    >
                      <div className="event-time-badge">
                        <span>
                          {formatUpcomingWeekday(event)}
                        </span>
                        <strong>
                          {formatUpcomingTime(event)}
                        </strong>
                      </div>

                      <div className="event-details">
                        <strong>{event.title}</strong>
                        <span>
                          {formatUpcomingDate(event)}
                        </span>
                        {event.location && <small>{event.location}</small>}
                      </div>
                    </button>
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