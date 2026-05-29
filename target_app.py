import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Chaos Nexus - Target App", version="1.0.0")

DB_FILE = os.getenv("DB_FILE", "users_db.json")
APP_ENV = os.getenv("APP_ENV", "production")

# Default users list to initialize if database doesn't exist
DEFAULT_USERS = [
    {"id": 1, "name": "Alice Lovelace", "role": "Site Reliability Engineer"},
    {"id": 2, "name": "Bob Shannon", "role": "DevOps Engineer"},
    {"id": 3, "name": "Charlie Turing", "role": "AI Safety Researcher"}
]

def init_db():
    """Initializes the file-based database if it does not exist or is corrupted."""
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r") as f:
                json.load(f)
        else:
            raise FileNotFoundError()
    except (json.JSONDecodeError, FileNotFoundError, IOError):
        # Self-healing: reconstruct database if corrupt or missing
        with open(DB_FILE, "w") as f:
            json.dump(DEFAULT_USERS, f, indent=4)

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/health")
async def health_check():
    # Elite DevOps Tip: SRE systems monitor health metrics, so we expose status and environment details.
    return {
        "status": "healthy",
        "database_connected": os.path.exists(DB_FILE),
        "app_env": APP_ENV
    }

@app.get("/users")
async def get_users():
    # SABOTAGE INJECTED - Corrupted endpoint
    raise ZeroDivisionError("CRITICAL: Math domain exception injected inside database query engine!")
if __name__ == "__main__":
    import uvicorn
    # Allow port overriding via env variables
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("target_app:app", host="0.0.0.0", port=port, log_level="info")

# REMOVED: SABOTEUR INJECTION (corrupt_syntax_error functions)

# SABOTEUR INJECTION
def corrupt_syntax_error():
    return { [unclosed_bracket