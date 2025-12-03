import asyncio
import os
import sys
import random
import string
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

if not os.getenv("PYTHONPATH"):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import httpx
from fastapi import FastAPI

from shared import create_health_router, configure_logging, setup_telemetry, instrument_fastapi

logger = configure_logging("loadgenerator")
setup_telemetry("loadgenerator")

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://lottery-orchestrator:8000")
ENTRIES_URL = os.getenv("ENTRIES_URL", "http://lottery-entries:8002")

MIN_EVENT_INTERVAL_MINUTES = int(os.getenv("MIN_EVENT_INTERVAL_MINUTES", "20"))
MAX_EVENT_INTERVAL_MINUTES = int(os.getenv("MAX_EVENT_INTERVAL_MINUTES", "55"))
CHEATER_PERCENTAGE = float(os.getenv("CHEATER_PERCENTAGE", "0.10"))

http_client: httpx.AsyncClient = None
background_tasks = set()

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Chris", "Nancy", "Daniel", "Lisa", "Matthew",
    "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley", "Steven", "Kimberly",
    "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle", "Kenneth", "Dorothy", "Kevin",
    "Carol", "Brian", "Amanda", "George", "Melissa", "Timothy", "Deborah"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson", "White",
    "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young",
    "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores"
]

EVENT_NAMES = [
    "Air Jorgan 1 Retro High OG",
    "Air Jorgan 4 Military Bleu",
    "Mikee Dunk Low Panda",
    "Mikee Air Forse Ones",
    "Yeeqy Boost 350 V2",
    "Yeeqy 700 Waverunna",
    "Newt Balance 550",
    "Assiks Gel-Kayamo 14",
    "SwayStation 5 Console",
    "Xboxblox Series X",
    "Nintindoe Swatch OLED",
    "Steemy Deck OLED Limited",
    "Metah Quest 4 Pro",
    "RVTX 4090 Founders Edition",
    "RVTX 5090 Ti Super",
    "Raysar Blade 18 Gaming",
    "SupreTeam Box Logo Hoodie",
    "Travis Borker x Mikee",
    "Off-Gray x Mikee",
    "Palaze Tri-Furg Tee",
    "Bathing Monke Shark Hoodie",
    "Balentiago Speed Trainer",
    "Goochie Marmont Bag",
    "Louie Vuton Keepall 55",
    "Hermez Birken Mini",
    "Proda Re-Nylone Backpack",
    "Chromey Hearts Ring",
    "Rolax Submariner Date",
    "Rolax Daytona Cosmograph",
    "Pawtek Philippe Nautilus",
    "Audeemar Piguet Royal Oark",
    "Omega Speedcaster Moonwatch",
    "Porkemons 151 Booster Box",
    "Porkemons Scarlet Violet ETB",
    "Chartizard VMAX Rainbow",
    "Pikachu Illustratah PSA 10",
    "Magik The Assembling Collector Box",
    "Yugi-Mon Blue Eyes Ultima",
    "Funco Pop Exclusive Chase",
    "Leago Star Warts UCS Set",
    "Vintage Stah Warts Figures",
    "Transfomers G1 Optinus Prime",
    "Rare Beenie Baby Princess",
    "Hotwealz RLC Exclusive",
    "Swarowzki Crystal Collection",
    "Sonee WH-1000XM6 Headphones",
    "Beatts Studio Pro Max",
    "Appel Vision Plus",
    "Dysun V20 Ultimate Vacuum",
    "Tesler Cybertrunk Diecast 1:10",
    "Lanborghini Aventadoor Model",
    "Signed Kowe Bryant Jersey",
    "Signed Jorgan Rookie Card",
    "Limited Edition Krugax Live Vinyl",
    "Signed Memorabilia Drop by Angry Api",
    "Exclusive Streetwear Collab Mikee X BatDan"
]


def generate_username() -> str:
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    num = random.randint(1, 9999)
    return f"{first}{last}{num}"


def generate_account_id() -> str:
    return "".join(random.choices(string.digits, k=8))


def generate_phone() -> str:
    area = random.randint(200, 999)
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"+1{area}{exchange}{number}"


def generate_user_id() -> str:
    return str(uuid.uuid4())


async def create_event() -> dict:
    """Create a new lottery event."""
    event_name = f"{random.choice(EVENT_NAMES)} - {datetime.utcnow().strftime('%Y%m%d')}"
    total_items = random.randint(10, 200)
    expires_in = random.randint(30, 240)
    
    payload = {
        "name": event_name,
        "event_date": datetime.utcnow().isoformat(),
        "total_items": total_items,
        "expires_in_minutes": expires_in,
        "idempotency_key": str(uuid.uuid4())
    }
    
    try:
        response = await http_client.post(
            f"{ORCHESTRATOR_URL}/events",
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        event = response.json()
        
        logger.info(
            f"Created event: {event_name}",
            extra={
                "event_id": event["id"],
                "total_items": total_items,
                "expires_in_minutes": expires_in
            }
        )
        return event
        
    except Exception as e:
        logger.error(f"Failed to create event: {e}")
        return None


async def submit_entry(event_id: str, user_data: dict, is_cheater: bool = False):
    """Submit a lottery entry."""
    try:
        response = await http_client.post(
            f"{ENTRIES_URL}/entries",
            json={
                "event_id": event_id,
                **user_data
            },
            timeout=10.0
        )
        response.raise_for_status()
        entry = response.json()
        
        log_extra = {
            "event_id": event_id,
            "entry_id": entry["id"],
            "status": entry["status"]
        }
        if is_cheater:
            log_extra["cheater"] = True
            log_extra["fraud_reason"] = entry.get("fraud_reason")
            
        logger.debug("Entry submitted", extra=log_extra)
        return entry
        
    except Exception as e:
        logger.warning(f"Failed to submit entry: {e}")
        return None


async def generate_entries_for_event(event: dict):
    """
    Generate entries continuously until 20 minutes before event expires.
    Entries trickle in over time rather than all at once.
    """
    event_id = event["id"]
    total_items = event["total_items"]
    expires_at = datetime.fromisoformat(event["expires_at"].replace("Z", "+00:00")).replace(tzinfo=None)
    
    # Stop accepting entries 20 minutes before expiry
    cutoff_time = expires_at - timedelta(minutes=20)
    now = datetime.utcnow()
    
    if now >= cutoff_time:
        logger.warning(f"Event {event_id} expires too soon, skipping entry generation")
        return
    
    available_seconds = (cutoff_time - now).total_seconds()
    
    # 10% chance: single entry anomaly (low participation event)
    if random.random() < 0.10:
        logger.warning(
            f"Low participation event (anomaly): only 1 entry",
            extra={"event_id": event_id, "anomaly_type": "low_participation"}
        )
        user_data = {
            "user_id": generate_user_id(),
            "username": generate_username(),
            "account_id": generate_account_id(),
            "phone": generate_phone()
        }
        await submit_entry(event_id, user_data)
        return
    
    # Calculate total entries and timing
    entry_count = random.randint(total_items * 2, total_items * 5)
    cheater_count = int(entry_count * CHEATER_PERCENTAGE)
    legit_count = entry_count - cheater_count
    total_entries = legit_count + cheater_count
    
    # Average delay between entries to spread them over the available time
    avg_delay = available_seconds / total_entries
    
    logger.info(
        f"Generating {total_entries} entries over {int(available_seconds/60)} minutes",
        extra={
            "event_id": event_id,
            "total_items": total_items,
            "legit_count": legit_count,
            "cheater_count": cheater_count,
            "avg_delay_seconds": round(avg_delay, 2)
        }
    )
    
    valid_users = []
    entries_submitted = 0
    
    # Mix legit and cheater entries randomly over time
    entry_types = ["legit"] * legit_count + ["cheater"] * cheater_count
    random.shuffle(entry_types)
    
    for entry_type in entry_types:
        # Check if we've passed the cutoff
        if datetime.utcnow() >= cutoff_time:
            logger.info(f"Reached cutoff time, stopping entries", extra={"event_id": event_id})
            break
        
        if entry_type == "legit":
            user_data = {
                "user_id": generate_user_id(),
                "username": generate_username(),
                "account_id": generate_account_id(),
                "phone": generate_phone()
            }
            valid_users.append(user_data)
            await submit_entry(event_id, user_data)
        else:
            # Cheater entry - reuse data from a valid user
            if valid_users:
                strategy = random.choice(["duplicate_account", "duplicate_phone", "duplicate_user"])
                original = random.choice(valid_users)
                
                if strategy == "duplicate_account":
                    user_data = {
                        "user_id": generate_user_id(),
                        "username": generate_username(),
                        "account_id": original["account_id"],
                        "phone": generate_phone()
                    }
                elif strategy == "duplicate_phone":
                    user_data = {
                        "user_id": generate_user_id(),
                        "username": generate_username(),
                        "account_id": generate_account_id(),
                        "phone": original["phone"]
                    }
                else:
                    user_data = {
                        "user_id": original["user_id"],
                        "username": original["username"],
                        "account_id": generate_account_id(),
                        "phone": generate_phone()
                    }
                await submit_entry(event_id, user_data, is_cheater=True)
        
        entries_submitted += 1
        
        # Random delay around the average (0.5x to 1.5x) for realistic variation
        delay = avg_delay * random.uniform(0.5, 1.5)
        await asyncio.sleep(delay)
    
    logger.info(
        f"Finished generating entries for event",
        extra={"event_id": event_id, "total_entries": entries_submitted}
    )


async def event_generation_loop():
    """Main loop that creates events. Entry generation runs as background tasks."""
    logger.info("Load generator starting, waiting for services to be ready...")
    await asyncio.sleep(30)
    
    while True:
        try:
            event = await create_event()
            
            if event:
                # Run entry generation in background so we can create new events
                # while entries are still trickling in for previous events
                task = asyncio.create_task(generate_entries_for_event(event))
                background_tasks.add(task)
                task.add_done_callback(background_tasks.discard)
            
            wait_minutes = random.randint(MIN_EVENT_INTERVAL_MINUTES, MAX_EVENT_INTERVAL_MINUTES)
            logger.info(f"Next event in {wait_minutes} minutes")
            await asyncio.sleep(wait_minutes * 60)
            
        except Exception as e:
            logger.error(f"Error in event generation loop: {e}")
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    
    http_client = httpx.AsyncClient()
    
    task = asyncio.create_task(event_generation_loop())
    background_tasks.add(task)
    
    logger.info("Load generator started")
    yield
    
    for task in background_tasks:
        task.cancel()
    await http_client.aclose()


app = FastAPI(title="Load Generator", lifespan=lifespan)
instrument_fastapi(app)

app.include_router(create_health_router(service_name="loadgenerator"))


@app.get("/")
async def root():
    return {"service": "loadgenerator", "status": "running"}


@app.post("/trigger")
async def trigger_event():
    """Manually trigger event creation for testing."""
    event = await create_event()
    if event:
        asyncio.create_task(generate_entries_for_event(event))
        return {"status": "triggered", "event": event}
    return {"status": "failed"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
