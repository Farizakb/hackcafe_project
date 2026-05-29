import os
import random
import time
import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Chaos Nexus - Saboteur Agent", version="1.0.0")

# In-memory history of chaos attacks
chaos_history = []

TARGET_APP_PATH = "target_app.py"
ENV_FILE_PATH = ".env"
DB_FILE_PATH = "users_db.json"

# Retry settings for container environment file locks
MAX_RETRIES = 3
RETRY_DELAY = 0.5

SABOTAGE_METHODS = [
    "syntax_error",
    "logical_error",
    "env_corruption",
    "database_corruption"
]

def corrupt_syntax():
    """Injects syntax-breaking python code into target_app.py with retry logic."""
    if not os.path.exists(TARGET_APP_PATH):
        return False, "Target application file target_app.py not found."
    
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * (attempt + 1))
                
            with open(TARGET_APP_PATH, "r", encoding="utf-8") as f:
                content = f.read()

            # Corrupt by appending syntax-breaking characters at the end
            corrupted_content = content + "\n\n# SABOTEUR INJECTION\ndef corrupt_syntax_error():\n    return { [unclosed_bracket"
            
            with open(TARGET_APP_PATH, "w", encoding="utf-8") as f:
                f.write(corrupted_content)
                f.flush()
                os.fsync(f.fileno())
                
            return True, "Injected unclosed list bracket syntax error into target_app.py."
        except (IOError, OSError) as e:
            if attempt == MAX_RETRIES - 1:
                return False, f"Failed to corrupt syntax after {MAX_RETRIES} attempts: {str(e)}"
            continue
    
    return False, "Syntax corruption failed due to file lock."

def corrupt_logic():
    """Modifies target_app.py to throw a runtime error on /users route."""
    if not os.path.exists(TARGET_APP_PATH):
        return False, "Target application file target_app.py not found."
    
    with open(TARGET_APP_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Replaces the normal get_users function with a broken one
    target_str = 'async def get_users():'
    if target_str not in content:
        return False, "Could not find get_users endpoint in target_app.py."

    # Locate the get_users function and replace it with a broken version
    lines = content.splitlines()
    start_idx = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith("async def get_users():"):
            start_idx = idx
            break
            
    if start_idx == -1:
        return False, "Could not locate start of get_users in target_app.py."
        
    # Find where get_users ends by checking indentation
    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        line = lines[idx]
        if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
            end_idx = idx
            break
    
    # Create corrupted function with proper indentation
    broken_lines = [
        "async def get_users():",
        "    # SABOTAGE INJECTED - Corrupted endpoint",
        "    raise ZeroDivisionError(\"CRITICAL: Math domain exception injected inside database query engine!\")"
    ]
            
    # Replace lines with our broken function
    new_lines = lines[:start_idx] + broken_lines + lines[end_idx:]
    with open(TARGET_APP_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))
        
    return True, "Injected logical ZeroDivisionError exception into the /users endpoint in target_app.py."

def corrupt_env():
    """Modifies the .env file to break database port configurations with retry logic."""
    if not os.path.exists(ENV_FILE_PATH):
        return False, f"Environment file {ENV_FILE_PATH} not found."
    
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * (attempt + 1))
                
            with open(ENV_FILE_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            # Inject corrupt DB_PORT env variable or modify if existing
            new_lines = []
            has_db_port = False
            for line in lines:
                if line.startswith("DB_PORT="):
                    new_lines.append("DB_PORT=invalid_non_integer_port_value_xyz\n")
                    has_db_port = True
                else:
                    new_lines.append(line)
                    
            if not has_db_port:
                new_lines.append("DB_PORT=invalid_non_integer_port_value_xyz\n")
                
            with open(ENV_FILE_PATH, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
                f.flush()
                os.fsync(f.fileno())
                
            return True, "Corrupted environment variable file (.env) by setting DB_PORT to a malformed non-integer string."
        except (IOError, OSError) as e:
            if attempt == MAX_RETRIES - 1:
                return False, f"Failed to corrupt env after {MAX_RETRIES} attempts: {str(e)}"
            continue
    
    return False, "Env corruption failed due to file lock."

def corrupt_database():
    """Overwrites users_db.json database with corrupted junk with retry logic."""
    junk_data = "☠️ SYSTEM_CORRUPTION_PAYLOAD_DEVOPS_NEXUS_BAD_SECTOR_CRITICAL ☠️"
    
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                time.sleep(RETRY_DELAY * (attempt + 1))
                
            with open(DB_FILE_PATH, "w", encoding="utf-8") as f:
                f.write(junk_data)
                f.flush()
                os.fsync(f.fileno())
            return True, "Overwrote users_db.json mock database file with non-JSON corrupted garbage."
        except (IOError, OSError) as e:
            if attempt == MAX_RETRIES - 1:
                return False, f"Failed to corrupt database after {MAX_RETRIES} attempts: {str(e)}"
            continue
    
    return False, "Database corruption failed due to file lock."

@app.get("/trigger-chaos")
@app.post("/trigger-chaos")
async def trigger_chaos():
    """
    Randomly chooses a sabotage method, executes it, logs the attack, and returns the result.
    """
    method = random.choice(SABOTAGE_METHODS)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    
    success = False
    details = ""
    
    if method == "syntax_error":
        success, details = corrupt_syntax()
    elif method == "logical_error":
        success, details = corrupt_logic()
    elif method == "env_corruption":
        success, details = corrupt_env()
    elif method == "database_corruption":
        success, details = corrupt_database()
        
    attack_record = {
        "id": len(chaos_history) + 1,
        "timestamp": timestamp,
        "method": method,
        "success": success,
        "details": details
    }
    
    chaos_history.append(attack_record)
    
    return JSONResponse(content={
        "status": "success" if success else "failed",
        "attack": attack_record
    })

@app.get("/chaos-history")
async def get_chaos_history():
    """Returns the list of all sabotage actions executed during the run."""
    return JSONResponse(content=chaos_history)

if __name__ == "__main__":
    import uvicorn
    # Expose Saboteur on port 8001
    uvicorn.run("saboteur_agent:app", host="0.0.0.0", port=8001, log_level="info")
