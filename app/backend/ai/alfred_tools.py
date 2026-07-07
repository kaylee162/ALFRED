ALFRED_TOOLS = [
    {
        "type": "function",
        "name": "create_calendar_event",
        "description": "Create a Google Calendar event.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The event title."},
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

    # Project tools
    {
        "type": "function",
        "name": "list_projects",
        "description": "Show the user's project folders from the allowed project directories, including src and source.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_project_folder",
        "description": "List folders and files inside a specific project folder path.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": ["string", "null"],
                    "description": "Folder path to list. Use null to show the default project root.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "open_project_path",
        "description": "Open a project folder in VS Code.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project folder path to open in VS Code.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },

    # File manager tools
    {
        "type": "function",
        "name": "search_files",
        "description": "Search safe folders for files or folders by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "File or folder name to search for.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                },
            },
            "required": ["query", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_folder",
        "description": "List the contents of a safe folder such as Downloads, Documents, Desktop, src, or source.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": ["string", "null"],
                    "description": "Folder path to list. Use null for Downloads.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "recent_downloads",
        "description": "Show recently downloaded files from the Downloads folder.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "How many days back to search.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recent downloads to return.",
                },
            },
            "required": ["days", "limit"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "read_text_file",
        "description": "Read a text, code, markdown, JSON, CSV, HTML, or CSS file so ALFRED can summarize it.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the text-based file to read.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "open_path",
        "description": "Open a safe file or folder in File Explorer.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Safe file or folder path to open.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_today",
            "description": "Get today's weather, including current temperature, humidity, high, low, and rain chance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_tomorrow",
            "description": "Get tomorrow's weather forecast.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_week",
            "description": "Get the weather forecast for the next 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_high_today",
            "description": "Get today's high temperature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_humidity_today",
            "description": "Get today's current humidity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rain_chance_tomorrow",
            "description": "Get tomorrow's chance of rain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City or location. Default is Atlanta."}
                },
                "required": []
            },
        },
    },

    
]