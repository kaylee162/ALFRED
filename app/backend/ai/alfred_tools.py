"""Tool schemas exposed to Ollama.

Every tool uses Ollama's canonical function-calling shape.
To add a future tool, add its schema to ``ALFRED_TOOLS`` and connect the
implementation in ``ai/tool_executor.py``.
"""

ALFRED_TOOLS = [{'type': 'function',
  'function': {'name': 'create_calendar_event',
               'description': 'Create a Google Calendar event.',
               'parameters': {'type': 'object',
                              'properties': {'title': {'type': 'string',
                                                       'description': 'The event title.'},
                                             'start_datetime': {'type': 'string',
                                                                'description': 'The event start '
                                                                               'datetime in ISO '
                                                                               'format.'},
                                             'end_datetime': {'type': 'string',
                                                              'description': 'The event end '
                                                                             'datetime in ISO '
                                                                             'format.'},
                                             'location': {
                                                            "type": ["string", "null"],
                                                            "description": (
                                                                "Optional city or location. "
                                                                "Leave null if the user did not specify a location. "
                                                                "Never invent a city."
                                                            ),
                                                        },
                                             'description': {'type': ['string', 'null'],
                                                             'description': 'Optional event '
                                                                            'description.'},
                                             'reminder_minutes': {'type': ['integer', 'null'],
                                                                  'description': 'Minutes before '
                                                                                 'the event to '
                                                                                 'show a '
                                                                                 'reminder.'}},
                              'required': ['title', 'start_datetime', 'end_datetime'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'get_calendar_day',
               'description': 'Get calendar events for one specific day.',
               'parameters': {'type': 'object',
                              'properties': {'date': {'type': 'string',
                                                      'description': 'Date in YYYY-MM-DD format.'}},
                              'required': ['date'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'get_upcoming_calendar_events',
               'description': 'Get upcoming calendar events.',
               'parameters': {'type': 'object',
                              'properties': {'days': {'type': 'integer',
                                                      'description': 'Number of days to look '
                                                                     'ahead.'},
                                             'max_results': {'type': 'integer',
                                                             'description': 'Maximum number of '
                                                                            'events to return.'}},
                              'required': ['days', 'max_results'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'plan_calendar_day',
               'description': 'Generate a daily plan based on calendar events.',
               'parameters': {'type': 'object',
                              'properties': {'date': {'type': 'string',
                                                      'description': 'Date in YYYY-MM-DD format.'}},
                              'required': ['date'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'summarize_calendar_week',
               'description': 'Generate a weekly calendar summary.',
               'parameters': {'type': 'object',
                              'properties': {'start_date': {'type': 'string',
                                                            'description': 'Week start date in '
                                                                           'YYYY-MM-DD format. Use '
                                                                           'Sunday as the start of '
                                                                           'the week.'}},
                              'required': ['start_date'],
                              'additionalProperties': False}}},
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
  'function': {'name': 'list_unread_emails',
               'description': "List unread emails in the user's Gmail inbox. Use when the user "
                              'asks to see, show, check, or list unread emails.',
               'parameters': {'type': 'object',
                              'properties': {'max_results': {'type': 'integer',
                                                             'description': 'Maximum number of '
                                                                            'unread emails to '
                                                                            'return. Default is '
                                                                            '10.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'list_recent_emails',
               'description': "List recent emails in the user's Gmail inbox. Use for requests such "
                              'as show my latest emails or what is new in my inbox.',
               'parameters': {'type': 'object',
                              'properties': {'max_results': {'type': 'integer',
                                                             'description': 'Maximum number of '
                                                                            'recent emails to '
                                                                            'return. Default is '
                                                                            '10.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'search_emails',
               'description': "Search the user's Gmail messages using Gmail search syntax. Use for "
                              'requests involving a sender, subject, keyword, date range, '
                              'attachments, read status, or mailbox label.',
               'parameters': {'type': 'object',
                              'properties': {'query': {'type': 'string',
                                                       'description': 'A Gmail search query, such '
                                                                      "as 'from:john@example.com', "
                                                                      "'subject:invoice', "
                                                                      "'newer_than:7d', "
                                                                      "'has:attachment', or "
                                                                      "'in:inbox is:unread'."},
                                             'max_results': {'type': 'integer',
                                                             'description': 'Maximum number of '
                                                                            'emails to return. '
                                                                            'Default is 10.'}},
                              'required': ['query'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'read_email',
               'description': 'Read the complete contents of a specific Gmail message. Use when a '
                              'message ID is already available from an earlier email result.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'The Gmail message ID '
                                                                           'of the email to read.'},
                                             'mark_as_read': {'type': 'boolean',
                                                              'description': 'Whether to mark the '
                                                                             'message as read. '
                                                                             'Default is true.'}},
                              'required': ['message_id'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'read_latest_email',
               'description': 'Read the newest email matching a Gmail search query. Use for '
                              'requests such as read my newest email, read my latest unread email, '
                              'or read the latest email from someone.',
               'parameters': {'type': 'object',
                              'properties': {'query': {'type': 'string',
                                                       'description': 'Gmail search query used to '
                                                                      'choose the newest matching '
                                                                      "email. Use 'in:inbox' when "
                                                                      'no filter was requested.'},
                                             'mark_as_read': {'type': 'boolean',
                                                              'description': 'Whether to mark the '
                                                                             'email as read. '
                                                                             'Default is true.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'summarize_email',
               'description': 'Read and summarize one specific email. Use when a Gmail message ID '
                              'is already known.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'The Gmail message ID '
                                                                           'of the email to '
                                                                           'summarize.'}},
                              'required': ['message_id'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'summarize_emails',
               'description': 'Create a concise briefing from several Gmail messages. Use for '
                              'summarize my inbox, summarize unread emails, what needs my '
                              'attention, or summarize emails from a sender.',
               'parameters': {'type': 'object',
                              'properties': {'query': {'type': 'string',
                                                       'description': 'Gmail search query '
                                                                      'selecting emails to '
                                                                      "summarize. Use 'in:inbox "
                                                                      "is:unread' for a general "
                                                                      'unread inbox summary.'},
                                             'max_results': {'type': 'integer',
                                                             'description': 'Maximum number of '
                                                                            'emails to summarize. '
                                                                            'Default is 10.'}},
                              'required': [],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'create_email_draft',
               'description': 'Create a Gmail draft for the user to review. Use this for write, '
                              'compose, draft, or prepare an email. Do not send the email.',
               'parameters': {'type': 'object',
                              'properties': {'to': {'type': 'string',
                                                    'description': 'Recipient email address.'},
                                             'subject': {'type': 'string',
                                                         'description': 'Email subject.'},
                                             'body': {'type': 'string',
                                                      'description': 'Complete email body.'},
                                             'cc': {'type': ['string', 'null'],
                                                    'description': 'Optional comma-separated CC '
                                                                   'recipients.'},
                                             'bcc': {'type': ['string', 'null'],
                                                     'description': 'Optional comma-separated BCC '
                                                                    'recipients.'}},
                              'required': ['to', 'subject', 'body'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'create_reply_draft',
               'description': 'Create a draft reply to an existing Gmail message without sending '
                              'it. Use when the user asks to write, draft, or prepare a reply.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'Gmail message ID being '
                                                                           'replied to.'},
                                             'body': {'type': 'string',
                                                      'description': 'Complete reply body.'}},
                              'required': ['message_id', 'body'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'send_email',
               'description': 'Send an email immediately. Only use when the user explicitly says '
                              'to send the email now. For write, compose, prepare, or draft '
                              'requests, use create_email_draft instead.',
               'parameters': {'type': 'object',
                              'properties': {'to': {'type': 'string',
                                                    'description': 'Recipient email address.'},
                                             'subject': {'type': 'string',
                                                         'description': 'Email subject.'},
                                             'body': {'type': 'string',
                                                      'description': 'Complete email body.'},
                                             'cc': {'type': ['string', 'null'],
                                                    'description': 'Optional comma-separated CC '
                                                                   'recipients.'},
                                             'bcc': {'type': ['string', 'null'],
                                                     'description': 'Optional comma-separated BCC '
                                                                    'recipients.'}},
                              'required': ['to', 'subject', 'body'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'send_email_draft',
               'description': 'Send an existing Gmail draft. Only use after the user explicitly '
                              'confirms that the saved draft should be sent.',
               'parameters': {'type': 'object',
                              'properties': {'draft_id': {'type': 'string',
                                                          'description': 'The Gmail draft ID to '
                                                                         'send.'}},
                              'required': ['draft_id'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'mark_email_read',
               'description': 'Mark a specific Gmail message as read.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'The Gmail message '
                                                                           'ID.'}},
                              'required': ['message_id'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'mark_email_unread',
               'description': 'Mark a specific Gmail message as unread.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'The Gmail message '
                                                                           'ID.'}},
                              'required': ['message_id'],
                              'additionalProperties': False}}},
 {'type': 'function',
  'function': {'name': 'archive_email',
               'description': 'Archive a specific Gmail message by removing it from the inbox. '
                              'This does not delete the email.',
               'parameters': {'type': 'object',
                              'properties': {'message_id': {'type': 'string',
                                                            'description': 'The Gmail message '
                                                                           'ID.'}},
                              'required': ['message_id'],
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