const API_BASE = "http://localhost:8000";

type RequestOptions = RequestInit;

type CalendarEventPayload = {
  title: string;
  start_time: string;
  end_time: string;
  location?: string;
  description?: string;
  reminder_minutes?: number;
};

type CalendarEventFormPayload = {
  title: string;
  dateTime: string;
  location?: string;
  description?: string;
  durationMinutes?: number;
  reminderMinutes?: number;
};

type ReminderPayload = {
  title: string;
  reminder_time: string;
  reminder_minutes_before?: number;
};

async function requestJson(
  url: string,
  options: RequestOptions = {},
  errorMessage = "Request failed"
) {
  const res = await fetch(url, options);

  if (!res.ok) {
    throw new Error(errorMessage);
  }

  return res.json();
}

export async function connectCalendar() {
  return requestJson(
    `${API_BASE}/calendar/connect`,
    {},
    "Failed to connect calendar"
  );
}

export async function getUpcomingEvents(days = 7, maxResults = 20) {
  return requestJson(
    `${API_BASE}/calendar/upcoming?days=${days}&max_results=${maxResults}`,
    {},
    "Failed to fetch upcoming events"
  );
}

export async function getDayEvents(date: string) {
  return requestJson(
    `${API_BASE}/calendar/day?date=${encodeURIComponent(date)}`,
    {},
    "Failed to fetch day events"
  );
}

export async function createCalendarEvent({
  title,
  start_time,
  end_time,
  location = "",
  description = "",
  reminder_minutes = 10,
}: CalendarEventPayload) {
  return requestJson(
    `${API_BASE}/calendar/event`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title,
        start_time,
        end_time,
        location: location || null,
        description: description || null,
        reminder_minutes,
      }),
    },
    "Failed to create calendar event"
  );
}

export async function createCalendarEventFromForm({
  title,
  dateTime,
  location = "",
  description = "",
  durationMinutes = 60,
  reminderMinutes = 10,
}: CalendarEventFormPayload) {
  const start = new Date(dateTime);
  const end = new Date(start.getTime() + durationMinutes * 60 * 1000);

  return createCalendarEvent({
    title,
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    location,
    description,
    reminder_minutes: reminderMinutes,
  });
}

export async function updateCalendarEvent(
  eventId: string,
  eventData: CalendarEventPayload
) {
  return requestJson(
    `${API_BASE}/calendar/event/${encodeURIComponent(eventId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(eventData),
    },
    "Failed to update calendar event"
  );
}

export async function createReminder(reminderData: ReminderPayload) {
  return requestJson(
    `${API_BASE}/calendar/reminder`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(reminderData),
    },
    "Failed to create reminder"
  );
}

export async function getTomorrowPlan() {
  return requestJson(
    `${API_BASE}/calendar/plan/tomorrow`,
    {},
    "Failed to generate tomorrow plan"
  );
}

export async function getDayPlan(date: string) {
  return requestJson(
    `${API_BASE}/calendar/plan/day?date=${encodeURIComponent(date)}`,
    {},
    "Failed to generate day plan"
  );
}

export async function getWeeklyPlan(startDate: string) {
  return requestJson(
    `${API_BASE}/calendar/plan/week?start_date=${encodeURIComponent(startDate)}`,
    {},
    "Failed to generate weekly plan"
  );
}