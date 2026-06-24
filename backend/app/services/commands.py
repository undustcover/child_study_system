"""Unified command handler placeholder.

All student execution commands should eventually enter this service, whether
they come from a real BOX-3, the virtual device, scheduler events, or parent
correction actions in the web console.
"""

SUPPORTED_COMMANDS = {
    "START_STUDY",
    "PAUSE_STUDY",
    "RESUME_STUDY",
    "COMPLETE_STUDY",
    "SKIP_TASK",
    "QUERY_CURRENT_TASK",
    "QUERY_TODAY_PLAN",
    "EXTEND_CURRENT_TASK",
    "EXTEND_BREAK",
    "STOP_SPEAKING",
}
