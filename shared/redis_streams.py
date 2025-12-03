import asyncio
import json
import logging
from typing import Callable, Dict, List, Optional
import redis.asyncio as redis
from datetime import datetime

logger = logging.getLogger(__name__)


class RedisStreamClient:
    """Wrapper for Redis Streams with consumer group support."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None
        
    async def connect(self):
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        
    async def close(self):
        if self.redis:
            await self.redis.close()
            
    async def publish(self, stream: str, data: dict) -> str:
        """Publish a message to a stream. Returns message ID."""
        data["_timestamp"] = datetime.utcnow().isoformat()
        msg_id = await self.redis.xadd(stream, {"payload": json.dumps(data)})
        logger.info(f"Published to {stream}", extra={"stream": stream, "msg_id": msg_id})
        return msg_id
    
    async def ensure_consumer_group(self, stream: str, group: str):
        """Create consumer group if it doesn't exist."""
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info(f"Created consumer group {group} for stream {stream}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
                
    async def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        handler: Callable[[dict], None],
        batch_size: int = 10,
        block_ms: int = 5000
    ):
        """Consume messages from a stream with exponential backoff on failures."""
        await self.ensure_consumer_group(stream, group)
        backoff = 1
        max_backoff = 60
        
        while True:
            try:
                messages = await self.redis.xreadgroup(
                    groupname=group,
                    consumername=consumer,
                    streams={stream: ">"},
                    count=batch_size,
                    block=block_ms
                )
                
                if messages:
                    backoff = 1
                    for stream_name, stream_messages in messages:
                        for msg_id, msg_data in stream_messages:
                            try:
                                payload = json.loads(msg_data.get("payload", "{}"))
                                await handler(payload)
                                await self.redis.xack(stream, group, msg_id)
                            except Exception as e:
                                logger.error(f"Handler failed for {msg_id}: {e}")
                                
            except redis.ConnectionError as e:
                logger.warning(f"Redis connection error, backing off {backoff}s: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            except Exception as e:
                logger.error(f"Unexpected error in consumer: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)


# Stream names as constants
STREAM_EVENTS_CREATED = "events:created"
STREAM_EVENTS_EXPIRED = "events:expired"
STREAM_EVENTS_CLEANUP = "events:cleanup"
STREAM_WINNERS_SELECTED = "winners:selected"
STREAM_DRAW_COMPLETED = "draw:completed"

