"""
core/tools_schema.py — Canonical Gemini Tool Declarations

Shared schema defining all assistant capabilities for both local and cloud orchestration.
"""

TOOL_DECLARATIONS = [
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer's OS-level settings and hardware. Use this to change brightness, "
            "toggle Wi-Fi, change volume, lock the screen, sleep the display, or shut down/restart the computer. "
            "Also handles keyboard inputs (scrolling, typing, taking screenshots, window snapping)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Specific action if known (e.g., 'volume_up', 'volume_set', 'brightness_down', 'lock_screen', 'shutdown')"
                },
                "description": {
                    "type": "STRING",
                    "description": "Natural language description of what to do (e.g., 'turn the volume to 50%', 'put the computer to sleep')"
                },
                "value": {
                    "type": "STRING",
                    "description": "Any value associated with the action (e.g., '50' for volume level)"
                },
                "confirmed": {
                    "type": "STRING",
                    "description": "Pass 'yes' if the user explicitly confirmed a dangerous action like 'shutdown' or 'restart'."
                }
            },
            "required": []
        }
    },
    {
        "name": "dev_agent",
        "description": (
            "An autonomous coding agent that builds full projects, writes code, installs dependencies, "
            "runs the project, and automatically fixes errors. Use this when the user asks you to 'write a script', "
            "'build an app', 'code a program', or 'run a project'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {
                    "type": "STRING",
                    "description": "A very detailed description of what the project should do."
                },
                "language": {
                    "type": "STRING",
                    "description": "The programming language to use (e.g., 'python', 'javascript')"
                },
                "project_name": {
                    "type": "STRING",
                    "description": "A short, snake_case name for the project folder."
                }
            },
            "required": ["description"]
        }
    },
    {
        "name": "background_monitor",
        "description": (
            "Sets up a background monitor to check crypto prices, system RAM/CPU, or website uptime. "
            "Use this when the user asks to be alerted when a condition is met (e.g., 'tell me if RAM goes over 90%' or 'alert me if bitcoin drops below 50000')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "'add' to create a monitor (default), 'list' to see active monitors."
                },
                "type": {
                    "type": "STRING",
                    "description": "One of: 'system', 'crypto', 'website'"
                },
                "target": {
                    "type": "STRING",
                    "description": "What to monitor (e.g. 'ram', 'cpu', 'bitcoin', 'https://example.com')"
                },
                "threshold": {
                    "type": "NUMBER",
                    "description": "The threshold value (e.g. 90 for 90%, 50000 for $50k)"
                },
                "condition": {
                    "type": "STRING",
                    "description": "'above' or 'below'"
                },
                "interval": {
                    "type": "INTEGER",
                    "description": "How often to check in seconds (default 60)"
                }
            },
            "required": []
        }
    },
    {
        "name": "system_manager",
        "description": (
            "Checks the system health (CPU, RAM, disk, battery) and lists top resource-hogging apps. "
            "Can also be used to forcefully close or kill frozen or heavy applications."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "What to do: 'status' to check system health (default), or 'kill' to close an app."
                },
                "process_name": {
                    "type": "STRING",
                    "description": "The exact name of the process to kill (if action is 'kill'), e.g. 'chrome.exe' or 'Spotify'"
                },
                "pid": {
                    "type": "INTEGER",
                    "description": "The PID of the process to kill (if action is 'kill')"
                }
            },
            "required": []
        }
    },
    {
        "name": "check_instagram_messages",
        "description": (
            "Checks your Instagram inbox for any recent unread or direct messages. "
            "Use this when the user asks 'do I have any messages', 'check my instagram', or similar."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "clipboard_processor",
        "description": (
            "Instantly reads the current text copied to the user's Windows clipboard. "
            "Use this whenever the user asks you to read, analyze, or fix what they just copied to their clipboard."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "instagram_reply",
        "description": "Replies to a pending Instagram message or takes over the Instagram chat in auto-mode.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Must be 'take_over' to handle it automatically, or 'manual_reply' to send a specific text message."
                },
                "reply_text": {
                    "type": "STRING",
                    "description": "The exact message to send to the user if action is 'manual_reply'."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the Windows computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, Instagram DMs, or other messaging platform. Can also upload media to Instagram when mode=upload and media_path is supplied.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name for DMs"},
                "message_text": {"type": "STRING", "description": "The message to send or Instagram caption"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, Instagram, etc."},
                "mode":         {"type": "STRING", "description": "dm | upload (Instagram only; default: dm)"},
                "media_path":   {"type": "STRING", "description": "Optional image/video path for Instagram uploads"}
            },
            "required": ["platform"]
        }
    },
    {
        "name": "whatsapp_control",
        "description": (
            "Direct server-side WhatsApp controller. "
            "Send text messages, photos, PDFs, Word/Excel documents to any contact. "
            "Read recent incoming and outgoing messages to brief Abhay on his chats. "
            "Manage the VIP auto-reply whitelist (add_vip, remove_vip, list_vip), "
            "check WhatsApp status, or switch modes (notify_only, whitelist, auto_pilot)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "send_text | send_image | send_document | check_status | save_contact | read_messages | add_vip | remove_vip | list_vip | set_mode"
                },
                "recipient": {
                    "type": "STRING",
                    "description": "Contact name (e.g. 'Rahul', 'Mom', 'Boss') or phone number with country code (e.g. '+919876543210')"
                },
                "message": {
                    "type": "STRING",
                    "description": "Message text or media caption to send"
                },
                "file_path": {
                    "type": "STRING",
                    "description": "Path to local file or document to send as an attachment"
                },
                "phone": {
                    "type": "STRING",
                    "description": "Phone number when action is save_contact, add_vip, or remove_vip"
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum number of recent messages to return when action is read_messages (default: 10)"
                },
                "mode": {
                    "type": "STRING",
                    "description": "notify_only | whitelist | auto_pilot (when action is set_mode)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Windows Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "smart_home_control",
        "description": (
            "Controls connected smart-home devices such as Atomberg fans and TP-Link Kasa lights/plugs. "
            "Use when the user asks to turn devices on or off, set fan speed, change brightness, or control a room."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "Natural language smart-home command"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls the web browser. Use for: opening websites, searching the web, "
            "navigating pages, clicking elements, filling forms, scrolling, tabs, back/forward, "
            "refreshing, and any web-based task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | navigate | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | press | back | forward | refresh | open_tab | new_tab | switch_tab | list_tabs | close"},
                "url":         {"type": "STRING", "description": "URL for go_to action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up or down for scroll"},
                "key":         {"type": "STRING", "description": "Key name for press action"},
                "tab":         {"type": "INTEGER", "description": "1-based tab index for switch_tab"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: open, close, list, create, delete, move, copy, rename, read, write, find, disk usage, "
            "and organizing a desktop or any folder into subfolders by type/date. Can also be used to explore and manage files on a connected Android phone."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "open | close | list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | organize_folder | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home. For android, use paths like downloads, documents, photos, movies, root."},
                "target":      {"type": "STRING", "description": "If operating on an Android device, provide the device name or ID. Leave empty for PC local files."},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "mode":        {"type": "STRING", "description": "by_type or by_date for organize actions"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen. Use for direct OS interactions. Do not invoke simultaneously with autonomous_operator.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_processor",
        "description": (
            "Processes any file that the user has uploaded or dropped onto the interface. "
            "Use this when the user refers to an uploaded file and wants an action on it. "
            "Supports: images (describe/ocr/resize/compress/convert), PDFs (summarize/extract_text/to_word), "
            "text files (summarize/fix/reformat/translate), CSV/Excel (analyze/stats/filter/sort/convert), "
            "JSON/XML (validate/format/analyze), code files (explain/review/fix/optimize/run/document/test), "
            "audio (transcribe/trim/convert/info), video (trim/extract_audio/extract_frame/compress/transcribe/info)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "Full path to file"},
                "action": {"type": "STRING", "description": "Action by type"},
                "instruction": {"type": "STRING", "description": "Free-form instruction"},
                "format": {"type": "STRING", "description": "Target format for conversion"},
                "save": {"type": "BOOLEAN", "description": "Save result to file (default: true)"}
            },
            "required": []
        }
    },
    {
        "name": "presentation_builder",
        "description": (
            "Creates editable PowerPoint presentations (.pptx) from a structured slide outline. "
            "Use when the user asks for a deck, slideshow, presentation, pitch deck, or report slides."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Presentation title"},
                "subtitle": {"type": "STRING", "description": "Optional subtitle or audience line"},
                "theme": {"type": "STRING", "description": "Optional presentation theme"},
                "outline": {"type": "STRING", "description": "Slide-by-slide outline"},
                "output_path": {"type": "STRING", "description": "Optional output path for the .pptx"},
                "auto_open": {"type": "BOOLEAN", "description": "Open the file after creating it (default: true)"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "spreadsheet_builder",
        "description": (
            "Creates editable Excel workbooks (.xlsx) from structured sheet data. "
            "Use for trackers, tables, analysis workbooks, budgets, planners, and other spreadsheet requests."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Workbook title"},
                "output_path": {"type": "STRING", "description": "Optional output path for the .xlsx"},
                "auto_open": {"type": "BOOLEAN", "description": "Open the file after creating it (default: true)"},
            },
            "required": ["title"]
        }
    },
    {
        "name": "word_document",
        "description": (
            "Creates, edits, reads, summarizes, extracts text from, and opens editable Word documents (.docx). "
            "Use for Word document requests, letters, reports, headings, bullets, formatting edits."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "create | create_letter | create_report | read | summarize | append | open"},
                "file_path": {"type": "STRING", "description": "Existing .docx file path"},
                "output_path": {"type": "STRING", "description": "Optional output path"},
                "title": {"type": "STRING", "description": "Document title"},
                "content": {"type": "STRING", "description": "Main body content"},
                "open_after": {"type": "BOOLEAN", "description": "Open saved document (default: true)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "pdf_document",
        "description": (
            "Creates editable-style PDF documents (.pdf) from structured content or converts DOCX / text files into PDFs."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "create | create_report | create_letter | convert"},
                "file_path": {"type": "STRING", "description": "Existing file to convert"},
                "output_path": {"type": "STRING", "description": "Optional output path"},
                "title": {"type": "STRING", "description": "PDF title"},
                "content": {"type": "STRING", "description": "Main body content"},
                "auto_open": {"type": "BOOLEAN", "description": "Open file (default: true)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "shutdown_brahma",
        "description": "Shuts down the assistant completely.",
        "parameters": {"type": "OBJECT", "properties": {}}
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key": {"type": "STRING", "description": "Short snake_case key"},
                "value": {"type": "STRING", "description": "Concise value in English"}
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "update_memory",
        "description": (
            "Alter or update an existing personal fact in long-term memory when the user's situation changes "
            "(e.g., moved to a new city, changed preferences, updated project goals). "
            "Replaces the existing value for that category and key."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key": {"type": "STRING", "description": "Short snake_case key to update"},
                "new_value": {"type": "STRING", "description": "Updated concise value in English"}
            },
            "required": ["category", "key", "new_value"]
        }
    },
    {
        "name": "delete_memory",
        "description": (
            "Permanently delete or forget a fact from long-term memory when the user requests it or "
            "when information is obsolete/cancelled."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key": {"type": "STRING", "description": "Short snake_case key to delete"}
            },
            "required": ["category", "key"]
        }
    },
    {
        "name": "search_memory",
        "description": "Search long-term memory for specific facts, past projects, preferences, or details.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search keyword or topic to search for in memory"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "spotify_controller",
        "description": "Plays and controls music via Spotify and Google Chrome.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "search_play | play | pause | toggle | next | previous | volume_up | volume_down | mute | open_spotify"},
                "query": {"type": "STRING", "description": "Song title, artist name, album, or playlist"},
                "volume": {"type": "NUMBER", "description": "Volume level"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "calendar_scheduler",
        "description": "Manages calendar events, appointments, and schedules.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "add_event | list_events | check_day | delete_event | get_upcoming | export_ics"},
                "title": {"type": "STRING", "description": "Title or summary of meeting/event"},
                "date": {"type": "STRING", "description": "Date (YYYY-MM-DD or 'today', 'tomorrow')"},
                "time": {"type": "STRING", "description": "Time (HH:MM in 24h format)"},
                "duration_minutes": {"type": "NUMBER", "description": "Duration in minutes (default: 30)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "daily_briefing",
        "description": "Delivers a complete daily briefing including time, date, today's schedule, and headlines.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "Optional category: all (default), tech, world"}
            },
            "required": []
        }
    },
    {
        "name": "autonomous_operator",
        "description": (
            "Specialized autonomous computer vision operator agent for complex GUI workflows. "
            "Use ONLY for multi-step visual workflows where no direct tools exist (e.g. interacting with third-party desktop apps, complex visual forms). "
            "DO NOT use for simple tasks: use 'open_app' to open applications, 'computer_control' to type/click into open windows, "
            "'browser_control' or 'web_search' for searching the web, or 'terminal_agent' for terminal commands. "
            "NEVER call other tools concurrently with autonomous_operator."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {
                    "type": "STRING",
                    "description": "Clear natural language goal for the operator to accomplish on the user's laptop."
                },
                "max_steps": {
                    "type": "INTEGER",
                    "description": "Maximum vision-action steps to attempt (default: 10, max: 15)."
                },
                "target_app": {
                    "type": "STRING",
                    "description": "Optional application name to open or bring to focus before starting (e.g. 'chrome', 'spotify', 'notepad')."
                }
            },
            "required": ["goal"]
        }
    },
    {
        "name": "terminal_agent",
        "description": (
            "A self-healing PowerShell & Terminal command execution engineer. "
            "Executes PowerShell or CMD commands on the user's laptop (e.g., system diagnostics, network checks, ping, "
            "git operations, software package management with winget/pip/npm). "
            "If a command fails, it automatically analyzes the error stack trace, generates an automated fix, executes the fix, and retries the command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "The exact PowerShell or CMD command to execute."
                },
                "working_dir": {
                    "type": "STRING",
                    "description": "Optional directory path to execute the command in."
                },
                "auto_heal": {
                    "type": "BOOLEAN",
                    "description": "Automatically diagnose and fix errors if command fails (default: true)."
                },
                "shell": {
                    "type": "STRING",
                    "description": "'powershell' (default) or 'cmd'."
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "get_weather",
        "description": (
            "Fetches live, real-time weather conditions and forecasts via Open-Meteo. "
            "Returns temperature, humidity, precipitation, wind speed, and human-readable conditions."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "location": {
                    "type": "STRING",
                    "description": "City or location name (e.g. 'Mumbai', 'London', 'New York', 'Tokyo')."
                },
                "lat": {
                    "type": "NUMBER",
                    "description": "Optional direct latitude."
                },
                "lon": {
                    "type": "NUMBER",
                    "description": "Optional direct longitude."
                }
            },
            "required": ["location"]
        }
    },
    {
        "name": "geocode_location",
        "description": (
            "Geocodes a location or address to latitude/longitude, or reverse geocodes coordinates to an address using OpenStreetMap Nominatim."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "City or address to lookup (e.g. 'Eiffel Tower', 'Bangalore')."
                },
                "lat": {
                    "type": "NUMBER",
                    "description": "Latitude for reverse geocoding."
                },
                "lon": {
                    "type": "NUMBER",
                    "description": "Longitude for reverse geocoding."
                },
                "reverse": {
                    "type": "BOOLEAN",
                    "description": "True if looking up address from coordinates."
                }
            },
            "required": []
        }
    },
    {
        "name": "convert_currency",
        "description": (
            "Live currency conversion using Frankfurter / European Central Bank exchange rates. "
            "Converts amounts between USD, EUR, INR, GBP, JPY, CAD, AUD, and all major currencies."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "amount": {
                    "type": "NUMBER",
                    "description": "Amount of money to convert (e.g. 100)."
                },
                "from_currency": {
                    "type": "STRING",
                    "description": "3-letter source currency code (e.g. 'USD', 'EUR', 'INR'). Default: 'USD'."
                },
                "to_currency": {
                    "type": "STRING",
                    "description": "3-letter target currency code (e.g. 'INR', 'USD', 'EUR'). Default: 'INR'."
                }
            },
            "required": ["amount"]
        }
    },
    {
        "name": "wikipedia_summary",
        "description": (
            "Retrieves verified, factual encyclopedia article summaries and thumbnail image URLs from Wikipedia."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Topic, concept, historical event, or person to look up (e.g. 'Quantum computing', 'Alan Turing')."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "generate_chart",
        "description": (
            "Generates a chart or graph image URL using QuickChart. "
            "Supports bar, line, pie, doughnut, and radar charts. Returns a direct viewable and shareable image URL."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "chart_type": {
                    "type": "STRING",
                    "description": "'bar' | 'line' | 'pie' | 'doughnut' | 'radar' (default: 'bar')"
                },
                "labels": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Labels for the X-axis or chart categories (e.g. ['Jan', 'Feb', 'Mar'])."
                },
                "data": {
                    "type": "ARRAY",
                    "items": {"type": "NUMBER"},
                    "description": "Numerical values corresponding to the labels (e.g. [120, 190, 300])."
                },
                "dataset_label": {
                    "type": "STRING",
                    "description": "Legend label for the dataset (e.g. 'Sales', 'Hours Studied')."
                },
                "title": {
                    "type": "STRING",
                    "description": "Title displayed at the top of the chart."
                }
            },
            "required": ["labels", "data"]
        }
    },
    {
        "name": "get_advice",
        "description": (
            "Fetches a piece of random or topic-based life advice, wisdom, or practical thoughts from Advice Slip."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "Optional keyword or theme to search advice for (e.g. 'work', 'time', 'friendship')."
                }
            },
            "required": []
        }
    },
    {
        "name": "get_joke",
        "description": (
            "Fetches safe, filtered programming jokes, puns, or general humor from JokeAPI. All content is strictly safe-for-work."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "'Programming' | 'Miscellaneous' | 'Pun' | 'Any' (default: 'Programming,Miscellaneous')"
                }
            },
            "required": []
        }
    },
    {
        "name": "shorten_url",
        "description": (
            "Shortens a long web link or URL into a clean, compact TinyURL link for messaging or sharing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "The full long URL to shorten (e.g. 'https://en.wikipedia.org/wiki/Artificial_intelligence')."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "get_news",
        "description": (
            "Fetches breaking news headlines and top stories via GNews API and Google News. "
            "Filter by category (business, technology, sports, science, general) or topic keyword."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search keyword or topic (e.g. 'artificial intelligence', 'SpaceX', 'Indian economy')."
                },
                "category": {
                    "type": "STRING",
                    "description": "'general' | 'technology' | 'business' | 'sports' | 'science' (default: 'general')"
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Number of headlines to return (default: 5, max: 10)."
                }
            },
            "required": []
        }
    },
    {
        "name": "calendar_control",
        "description": (
            "Manages Google Calendar. "
            "List upcoming meetings and events, schedule new appointments, or delete/cancel calendar events."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list_events | create_event | delete_event"
                },
                "summary": {
                    "type": "STRING",
                    "description": "Title or summary of the event (e.g. 'Team Sync', 'Doctor Appointment')."
                },
                "start_time": {
                    "type": "STRING",
                    "description": "ISO start time (e.g. '2026-09-10T14:00:00Z') or date ('2026-09-10')."
                },
                "end_time": {
                    "type": "STRING",
                    "description": "Optional ISO end time (defaults to 1 hour after start)."
                },
                "description": {
                    "type": "STRING",
                    "description": "Optional notes or details for the event."
                },
                "location": {
                    "type": "STRING",
                    "description": "Optional physical location or meeting link."
                },
                "event_id": {
                    "type": "STRING",
                    "description": "Event ID required when action is delete_event."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "gmail_control",
        "description": (
            "Reads, searches, and sends emails through the user's Gmail account. "
            "List unread emails, read details of an email, or send a new email on the user's behalf."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list_emails | read_email | send_email"
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query for list_emails (e.g. 'is:unread', 'from:professor', 'newer_than:2d')."
                },
                "message_id": {
                    "type": "STRING",
                    "description": "Message ID when reading full content via read_email."
                },
                "to": {
                    "type": "STRING",
                    "description": "Recipient email address when action is send_email."
                },
                "subject": {
                    "type": "STRING",
                    "description": "Subject line when sending an email."
                },
                "body": {
                    "type": "STRING",
                    "description": "Body message text when sending an email."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "todoist_control",
        "description": (
            "Manages tasks and to-do checklists using Todoist. "
            "List active tasks, create new tasks with due dates and priority, complete tasks, or delete tasks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list_tasks | add_task | complete_task | delete_task"
                },
                "task_name": {
                    "type": "STRING",
                    "description": "Content or title of the task (e.g. 'Submit physics assignment', 'Buy groceries')."
                },
                "due_date": {
                    "type": "STRING",
                    "description": "Natural language due date (e.g. 'today', 'tomorrow at 5pm', 'next Monday')."
                },
                "priority": {
                    "type": "INTEGER",
                    "description": "Priority from 1 (normal) to 4 (urgent)."
                },
                "task_id": {
                    "type": "STRING",
                    "description": "Specific task ID if known."
                }
            },
            "required": ["action"]
        }
    }
]
