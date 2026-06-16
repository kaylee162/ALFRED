import { useEffect, useState } from "react";
import {
  connectCalendar,
  getUpcomingEvents,
  getTomorrowPlan,
  createReminder,
} from "../api/calendarApi";

function CalendarAssistant() {
  const [events, setEvents] = useState([]);
  const [plan, setPlan] = useState(null);
  const [status, setStatus] = useState("");

  async function handleConnect() {
    try {
      setStatus("Connecting...");
      const data = await connectCalendar();
      setStatus(data.message);
    } catch {
      setStatus("Could not connect Google Calendar.");
    }
  }

  async function loadEvents() {
    try {
      const data = await getUpcomingEvents(7);
      setEvents(data.events || []);
    } catch {
      setStatus("Could not load events.");
    }
  }

  async function loadTomorrowPlan() {
    try {
      const data = await getTomorrowPlan();
      setPlan(data);
    } catch {
      setStatus("Could not generate tomorrow plan.");
    }
  }

  async function testReminder() {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(9, 0, 0, 0);

    await createReminder({
      title: "Check ALFRED daily plan",
      reminder_time: tomorrow.toISOString(),
      reminder_minutes_before: 10,
    });

    setStatus("Reminder created.");
    loadEvents();
  }

  useEffect(() => {
    loadEvents();
  }, []);

  return (
    <section className="calendar-assistant">
      <div className="calendar-header">
        <div>
          <p className="section-kicker">calendar & planning</p>
          <h2>A.L.F.R.E.D. schedule assistant</h2>
        </div>

        <button onClick={handleConnect}>
          Connect Google Calendar
        </button>
      </div>

      {status && <p className="calendar-status">{status}</p>}

      <div className="calendar-actions">
        <button onClick={loadEvents}>View upcoming events</button>
        <button onClick={loadTomorrowPlan}>What should I focus on tomorrow?</button>
        <button onClick={testReminder}>Create test reminder</button>
      </div>

      <div className="calendar-grid">
        <div className="calendar-card">
          <h3>Upcoming Events</h3>

          {events.length === 0 ? (
            <p>No upcoming events found.</p>
          ) : (
            events.map((event) => (
              <div className="event-row" key={event.id}>
                <strong>{event.title}</strong>
                <span>{event.start}</span>
                {event.location && <small>{event.location}</small>}
              </div>
            ))
          )}
        </div>

        <div className="calendar-card">
          <h3>Tomorrow’s Plan</h3>

          {!plan ? (
            <p>Ask ALFRED what to focus on tomorrow.</p>
          ) : (
            <>
              <h4>Recommendations</h4>
              {plan.recommendations.map((item, index) => (
                <p key={index}>{item}</p>
              ))}

              <h4>Open Focus Blocks</h4>
              {plan.free_focus_blocks.length === 0 ? (
                <p>No clean focus blocks found.</p>
              ) : (
                plan.free_focus_blocks.map((block, index) => (
                  <p key={index}>
                    {block.start} - {block.end}
                  </p>
                ))
              )}

              <h4>Suggested Plan</h4>
              <ol>
                {plan.suggested_plan.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ol>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

export default CalendarAssistant;