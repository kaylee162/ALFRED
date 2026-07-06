ALFRED_TOOLS = [
    {
        "type": "function",
        "name": "create_calendar_event",
        "description": "Create a Google Calendar event.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "The event title.",
                },
                "start_datetime": {
                    "type": "string",
                    "description": "The event start datetime in ISO format.",
                },
                "end_datetime": {
                    "type": "string",
                    "description": "The event end datetime in ISO format.",
                },
                "location": {
                    "type": ["string", "null"],
                    "description": "Optional event location.",
                },
                "description": {
                    "type": ["string", "null"],
                    "description": "Optional event description.",
                },
                "reminder_minutes": {
                    "type": ["integer", "null"],
                    "description": "Minutes before the event to show a reminder.",
                },
            },
            "required": ["title", "start_datetime", "end_datetime"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_calendar_day",
        "description": "Get calendar events for one specific day.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                }
            },
            "required": ["date"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_upcoming_calendar_events",
        "description": "Get upcoming calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look ahead.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return.",
                },
            },
            "required": ["days", "max_results"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "plan_calendar_day",
        "description": "Generate a daily plan based on calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                }
            },
            "required": ["date"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "summarize_calendar_week",
        "description": "Generate a weekly calendar summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Week start date in YYYY-MM-DD format. Use Sunday as the start of the week.",
                }
            },
            "required": ["start_date"],
            "additionalProperties": False,
        },
    },
]