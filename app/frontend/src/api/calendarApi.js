const API_BASE = "http://localhost:8000";

export async function connectCalendar() {
  const res = await fetch(`${API_BASE}/calendar/connect`);
  if (!res.ok) throw new Error("Failed to connect calendar");
  return res.json();
}

export async function getUpcomingEvents(days = 7) {
  const res = await fetch(`${API_BASE}/calendar/upcoming?days=${days}`);
  if (!res.ok) throw new Error("Failed to fetch upcoming events");
  return res.json();
}

export async function createCalendarEvent(eventData) {
  const res = await fetch(`${API_BASE}/calendar/event`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(eventData),
  });

  if (!res.ok) throw new Error("Failed to create event");
  return res.json();
}

export async function createReminder(reminderData) {
  const res = await fetch(`${API_BASE}/calendar/reminder`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(reminderData),
  });

  if (!res.ok) throw new Error("Failed to create reminder");
  return res.json();
}

export async function getTomorrowPlan() {
  const res = await fetch(`${API_BASE}/calendar/plan/tomorrow`);
  if (!res.ok) throw new Error("Failed to generate tomorrow plan");
  return res.json();
}

export async function getWeeklyPlan(startDate) {
  const res = await fetch(`${API_BASE}/calendar/plan/week?start_date=${startDate}`);
  if (!res.ok) throw new Error("Failed to generate weekly plan");
  return res.json();
}