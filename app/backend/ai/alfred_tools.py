"""Tool schemas exposed to Ollama.

Every tool uses Ollama's canonical function-calling shape.
To add a future tool, add its schema to ``ALFRED_TOOLS`` and connect the
implementation in ``ai/tool_executor.py``.
"""

ALFRED_TOOLS = [
{"type": "function",
        "function": {
            "name": "calendar",
            "description": (
                "Handle Google Calendar requests written in natural language, "
                "including viewing, creating, finding, updating, rescheduling, "
                "renaming, and deleting events. Always pass the user's complete "
                "original calendar command unchanged. Do not guess event IDs, "
                "rewrite dates or times, or directly perform updates or deletes. "
                "The calendar intent layer returns structured views, candidate matches, "
                "proposed changes, and confirmation requirements. Never call any "
                "other calendar mutation tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The user's full original calendar request copied "
                            "exactly, without summarizing, rewriting, or resolving "
                            "dates and times."
                        ),
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
{'type': 'function',
  'function': {'name': 'list_projects',
               'description': "Show the user's project folders from the allowed project "
                              'directories, including src and source.',
               'parameters': {'type': 'object',
                              'properties': {},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'list_project_folder',
               'description': 'List folders and files inside a specific project folder path.',
               'parameters': {'type': 'object',
                              'properties': {'path': {'type': ['string', 'null'],
                                                      'description': 'Folder path to list. Use '
                                                                     'null to show the default '
                                                                     'project root.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'open_project_path',
               'description': 'Open a project folder in VS Code.',
               'parameters': {'type': 'object',
                              'properties': {'path': {'type': 'string',
                                                      'description': 'Project folder path to open '
                                                                     'in VS Code.'}},
                              'required': ['path'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'search_files',
               'description': 'Search safe folders for files or folders by name.',
               'parameters': {'type': 'object',
                              'properties': {'query': {'type': 'string',
                                                       'description': 'File or folder name to '
                                                                      'search for.'},
                                             'limit': {'type': 'integer',
                                                       'description': 'Maximum number of results '
                                                                      'to return.'}},
                              'required': ['query'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'list_folder',
               'description': 'List the contents of a safe folder such as Downloads, Documents, '
                              'Desktop, src, or source.',
               'parameters': {'type': 'object',
                              'properties': {'path': {'type': ['string', 'null'],
                                                      'description': 'Folder path to list. Use '
                                                                     'null for Downloads.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'recent_downloads',
               'description': 'Show recently downloaded files from the Downloads folder.',
               'parameters': {'type': 'object',
                              'properties': {'days': {'type': 'integer',
                                                      'description': 'How many days back to '
                                                                     'search.'},
                                             'limit': {'type': 'integer',
                                                       'description': 'Maximum number of recent '
                                                                      'downloads to return.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'read_text_file',
               'description': 'Read a text, code, markdown, JSON, CSV, HTML, or CSS file so ALFRED '
                              'can summarize it.',
               'parameters': {'type': 'object',
                              'properties': {'path': {'type': 'string',
                                                      'description': 'Path of the text-based file '
                                                                     'to read.'}},
                              'required': ['path'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'open_path',
               'description': 'Open a safe file or folder in File Explorer.',
               'parameters': {'type': 'object',
                              'properties': {'path': {'type': 'string',
                                                      'description': 'Safe file or folder path to '
                                                                     'open.'}},
                              'required': ['path'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'gmail',
               'description': "Handle every Gmail request written in natural language, including listing, searching, reading, summarizing, searching saved drafts, editing draft recipients/CC/BCC/subject/body, drafting, replying, sending drafts, sending messages, marking read or unread, and archiving. Always pass the user's complete original Gmail request unchanged. Do not invent message IDs, draft IDs, recipients, subjects, or email content. The Gmail intent layer owns message selection, follow-up context, validation, previews, confirmations, and all Gmail API calls.",
               'parameters': {'type': 'object',
                              'properties': {'command': {'type': 'string',
                                                         'description': "The user's complete original Gmail request copied exactly without summarizing, rewriting, or resolving references."}},
                              'required': ['command'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'weather',
               'description': 'Get current weather or forecasts for a location, including '
                              'temperature, high, low, humidity, and rain chance.',
               'parameters': {'type': 'object',
                              'properties': {'location': {'type': 'string',
                                                          'description': 'City or location. Use '
                                                                         'Atlanta when omitted.'},
                                             'period': {'type': 'string',
                                                        'enum': ['today', 'tomorrow', 'week'],
                                                        'description': 'Forecast period requested '
                                                                       'by the user.'},
                                             'detail': {'type': 'string',
                                                        'enum': ['summary',
                                                                 'high',
                                                                 'humidity',
                                                                 'rain_chance'],
                                                        'description': 'Use summary for a normal '
                                                                       'forecast. High and '
                                                                       'humidity apply to today. '
                                                                       'Rain chance applies to '
                                                                       'tomorrow.'}},
                              'required': ['period', 'detail'],
                              'additionalProperties': False}}}]