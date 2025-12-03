import logging
import json
import sys
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
            
        for key in ["event_id", "user_id", "account_id", "stream", "msg_id", 
                    "winner_count", "entry_count", "fraud_reason", "phone"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)
                
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)


def configure_logging(service_name: str, level: str = "INFO"):
    """Configure structured JSON logging for a service."""
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper()))
    
    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return logging.getLogger(service_name)

