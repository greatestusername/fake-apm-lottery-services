from prometheus_client import Counter, Histogram, Gauge

# Orchestrator metrics
EVENTS_CREATED = Counter("lottery_events_created_total", "Total lottery events created")
EVENTS_EXPIRED = Counter("lottery_events_expired_total", "Total lottery events expired")
EVENTS_COMPLETED = Counter("lottery_events_completed_total", "Total lottery events completed")
ACTIVE_EVENTS = Gauge("lottery_active_events", "Number of currently active events")

# Entries metrics
ENTRIES_SUBMITTED = Counter(
    "lottery_entries_submitted_total", 
    "Total entries submitted",
    ["status"]  # VALID, INVALID
)
ENTRIES_BY_EVENT = Gauge("lottery_entries_by_event", "Entries per event", ["event_id"])
FRAUD_DETECTED = Counter(
    "lottery_fraud_detected_total",
    "Fraud patterns detected",
    ["reason"]  # duplicate_account, duplicate_phone, duplicate_user
)

# Draw metrics
DRAWS_EXECUTED = Counter("lottery_draws_executed_total", "Total draws executed")
WINNERS_SELECTED = Counter("lottery_winners_selected_total", "Total winners selected")
DRAW_DURATION = Histogram(
    "lottery_draw_duration_seconds",
    "Time to execute a draw",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Notification metrics
NOTIFICATIONS_SENT = Counter(
    "lottery_notifications_sent_total",
    "Total notifications sent",
    ["type"]  # event_announce, winner_notify
)
NOTIFICATION_LATENCY = Histogram(
    "lottery_notification_latency_seconds",
    "Simulated notification latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0]
)

# Redis stream metrics
STREAM_MESSAGES_PUBLISHED = Counter(
    "lottery_stream_messages_published_total",
    "Messages published to Redis streams",
    ["stream"]
)
STREAM_MESSAGES_CONSUMED = Counter(
    "lottery_stream_messages_consumed_total",
    "Messages consumed from Redis streams",
    ["stream", "consumer_group"]
)

