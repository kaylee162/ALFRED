const API_BASE = "http://localhost:8000";

type CalendarCreatePayload = {
  title: string;
  start_time?: string;
  end_time?: string;
  start_date?: string;
  end_date?: string;
  all_day?: boolean;
  description?: string | null;
  location?: string | null;
  reminder_minutes?: number | null;
  calendar_id?: string;
};

type CalendarUpdatePayload = Partial<CalendarCreatePayload>;

async function readJson(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.message || "Calendar request failed.");
  }
  return data;
}

export async function createCalendarEvent(payload: CalendarCreatePayload) {
  const response = await fetch(`${API_BASE}/calendar/event`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function updateCalendarEvent(
  eventId: string,
  payload: CalendarUpdatePayload
) {
  const response = await fetch(`${API_BASE}/calendar/event/${encodeURIComponent(eventId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readJson(response);
}

export async function deleteCalendarEvent(
  eventId: string,
  calendarId = "primary"
) {
  const params = new URLSearchParams({ calendar_id: calendarId });
  const response = await fetch(
    `${API_BASE}/calendar/event/${encodeURIComponent(eventId)}?${params.toString()}`,
    { method: "DELETE" }
  );
  return readJson(response);
}
