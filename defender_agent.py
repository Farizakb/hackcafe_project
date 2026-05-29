import os
import re
import time
import httpx
import asyncio
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

TARGET_APP_URL = "http://localhost:8000"
DASHBOARD_URL = "http://localhost:8080"
TARGET_APP_LOG = "target_app.log"
TARGET_APP_PATH = "target_app.py"
ENV_FILE_PATH = ".env"
DB_FILE_PATH = "users_db.json"

# Retry settings for container file access
READ_RETRIES = 2
READ_RETRY_DELAY = 0.2

# Retrieve API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("[DEFENDER] WARNING: GEMINI_API_KEY not found in env. Self-healing might fail.")
else:
    genai.configure(api_key=api_key)

async def post_dashboard_log(event_type: str, message: str, details: str = ""):
    """Sends log messages to the central orchestrator dashboard."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{DASHBOARD_URL}/log-defender", json={
                "event_type": event_type,
                "message": message,
                "details": details
            })
    except Exception as e:
        print(f"[DEFENDER] Dashboard log post failed: {e}")

def get_last_logs(file_path: str, line_count: int = 50) -> str:
    """Reads the last N lines from a log file with retry logic."""
    if not os.path.exists(file_path):
        return "Log file not found."
    
    for attempt in range(READ_RETRIES):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                return "".join(lines[-line_count:])
        except (IOError, OSError) as e:
            if attempt == READ_RETRIES - 1:
                return f"Error reading logs after {READ_RETRIES} attempts: {str(e)}"
            time.sleep(READ_RETRY_DELAY * (attempt + 1))
        except Exception as e:
            return f"Error reading logs: {str(e)}"
    
    return "Failed to read log file."

def read_file_safely(file_path: str) -> str:
    """Reads file contents safely with retry logic for container environments."""
    if not os.path.exists(file_path):
        return f"File {file_path} does not exist."
    
    for attempt in range(READ_RETRIES):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (IOError, OSError) as e:
            if attempt == READ_RETRIES - 1:
                return f"Error reading file {file_path} after {READ_RETRIES} attempts: {str(e)}"
            time.sleep(READ_RETRY_DELAY * (attempt + 1))
        except Exception as e:
            return f"Error reading file {file_path}: {str(e)}"
    
    return f"Failed to read {file_path}"

async def query_gemini_healer(error_context: str) -> str:
    """Queries Gemini 3.5 Flash to generate a self-healing patch."""
    if not api_key:
        return "ERROR: GEMINI_API_KEY is not set."

    # Read current state of code/config/data to give Gemini full context
    target_code = read_file_safely(TARGET_APP_PATH)
    env_content = read_file_safely(ENV_FILE_PATH)
    # Redact sensitive key before sending to LLM
    redacted_env = re.sub(r'GEMINI_API_KEY="[^"]+"', 'GEMINI_API_KEY="REDACTED"', env_content)
    
    db_content = read_file_safely(DB_FILE_PATH)
    if len(db_content) > 1000:
        db_content = db_content[:1000] + "\n... [TRUNCATED] ..."

    prompt = f"""
You are an Elite Principal SRE (Site Reliability Engineer) and Agentic AI healer.
The Target Application (FastAPI) has crashed or failed health checks.

=== SYSTEM DIAGNOSTICS & ERROR DETAILS ===
{error_context}

=== CURRENT TARGET_APP.PY CODE ===
```python
{target_code}
```

=== CURRENT .ENV CONFIG ===
```env
{redacted_env}
```

=== CURRENT USERS_DB.JSON CONTENT ===
```json
{db_content}
```

=== TASK ===
Diagnose the root cause of this failure and write a complete, flawless patch.
You MUST output your response in strict Markdown format exactly as follows:

### Root Cause
<Clear, technical explanation of what caused the crash/failure based on the logs and current state>

### Patch
In this section, output a single Markdown code block containing the COMPLETE, FIXED content of the file that was sabotaged. 
The code block MUST start with a file comment header like `# FILE: <filename>` to specify which file needs replacement.
Available files you can patch: `target_app.py`, `.env`, or `users_db.json`.

Example of patching target_app.py:
```python
# FILE: target_app.py
import os
# ... rest of the complete target_app.py code with the fix implemented ...
```

Example of patching users_db.json:
```json
# FILE: users_db.json
[
    {{"id": 1, "name": "Alice Lovelace", "role": "Site Reliability Engineer"}}
]
```

Example of patching .env:
```env
# FILE: .env
DB_PORT=5432
GEMINI_API_KEY="KEEP_EXISTING_KEY"
```
NOTE: If patching .env, preserve the original GEMINI_API_KEY value or set it back using the placeholder "KEEP_EXISTING_KEY", and the defender agent will preserve the actual key.

### System Recovery Logs
<Summary of SRE recovery steps executed to restore the system>

Do not include any other text outside these three sections. Ensure the patch is complete with no omissions or placeholders.
"""
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = await asyncio.to_thread(model.generate_content, prompt)
        return response.text
    except Exception as e:
        return f"Gemini API failure: {str(e)}"

def apply_patch(patch_filename: str, patch_content: str):
    """Saves the generated patch back to the filesystem."""
    # Special handle for .env to preserve the original GEMINI_API_KEY
    if patch_filename == ".env":
        original_key = None
        if os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        original_key = line.strip()
                        break
        
        # Split patch lines and write
        lines = patch_content.splitlines()
        final_lines = []
        for line in lines:
            if "GEMINI_API_KEY=" in line and original_key:
                final_lines.append(original_key + "\n")
            elif not line.startswith("# FILE:"):
                final_lines.append(line + "\n")
        
        with open(ENV_FILE_PATH, "w") as f:
            f.writelines(final_lines)
            
    elif patch_filename in ["target_app.py", "users_db.json"]:
        # Strip the file header line if present
        lines = patch_content.splitlines()
        if lines and (lines[0].startswith("# FILE:") or lines[0].startswith("// FILE:")):
            lines = lines[1:]
        
        cleaned_content = "\n".join(lines)
        with open(patch_filename, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
    else:
        raise ValueError(f"Unauthorized file write request for: {patch_filename}")

async def inspect_loop():
    """Main self-healing inspection loop that monitors target health."""
    print("[DEFENDER] Starting autonomous SRE inspection loop...")
    await asyncio.sleep(2.0)  # Wait for services to fully initialize
    
    consecutive_successes = 0

    while True:
        await asyncio.sleep(3.0)
        
        is_healthy = False
        error_context = ""
        
        try:
            async with httpx.AsyncClient() as client:
                # Query both health and users endpoint to ensure full operability
                health_resp = await client.get(f"{TARGET_APP_URL}/health", timeout=2.0)
                users_resp = await client.get(f"{TARGET_APP_URL}/users", timeout=2.0)
                
                if health_resp.status_code == 200 and users_resp.status_code == 200:
                    is_healthy = True
                    consecutive_successes += 1
                else:
                    error_context = f"Health endpoint returned status {health_resp.status_code} with {health_resp.text}. Users endpoint returned status {users_resp.status_code} with {users_resp.text}."
        except httpx.ConnectError:
            error_context = "CRITICAL: Connection Refused! The Target Process is down or failed to startup."
        except httpx.TimeoutException:
            error_context = "CRITICAL: Request Timeout! The Target Application is unresponsive."
        except Exception as e:
            error_context = f"CRITICAL: Unexpected network/http failure: {str(e)}"
            
        if is_healthy:
            # SRE metric logging
            if consecutive_successes % 5 == 0:
                print(f"[DEFENDER] System is operating normally (Health: OK).")
            continue
            
        consecutive_successes = 0
        print(f"\n[DEFENDER] [!] FAILURE DETECTED: {error_context}")
        await post_dashboard_log(
            event_type="DISPATCH", 
            message="Alert triggered! Commencing auto-healing diagnostics...",
            details=error_context
        )
        
        # Read target app terminal logs to catch traceback
        app_logs = get_last_logs(TARGET_APP_LOG, 40)
        full_error_context = f"{error_context}\n\n=== RECENT APP RUNTIME LOGS ===\n{app_logs}"
        
        print("[DEFENDER] Consulting Gemini self-healing brain...")
        healing_md = await query_gemini_healer(full_error_context)
        
        # Parse the healing Markdown
        root_cause = "Unknown"
        patch_file = None
        patch_content = None
        recovery_logs = ""
        
        # Extract root cause
        rc_match = re.search(r"### Root Cause\s+(.*?)\s+(?=###)", healing_md, re.DOTALL)
        if rc_match:
            root_cause = rc_match.group(1).strip()
            
        # Extract recovery logs
        rl_match = re.search(r"### System Recovery Logs\s+(.*)", healing_md, re.DOTALL)
        if rl_match:
            recovery_logs = rl_match.group(1).strip()
            
        # Extract patch and target file using improved regex
        # Pattern: ``` [optional language] \n # FILE: filename \n content \n ```
        patch_match = re.search(r'```(?:python|json|env)?\s*\n\s*#\s*FILE:\s*(\S+)\s*\n(.*?)\n```', healing_md, re.DOTALL)
        if patch_match:
            patch_file = patch_match.group(1).strip()
            patch_content = patch_match.group(2).strip()
            
        if patch_file and patch_content:
            print(f"[DEFENDER] Applying patch to: {patch_file}")
            try:
                apply_patch(patch_file, patch_content)
                print("[DEFENDER] Patch successfully applied to disk.")
                
                # Signal orchestrator dashboard to restart target application
                async with httpx.AsyncClient() as client:
                    restart_resp = await client.post(f"{DASHBOARD_URL}/restart-target")
                    
                if restart_resp.status_code == 200:
                    print("[DEFENDER] Target application reload triggered successfully.")
                    await post_dashboard_log(
                        event_type="HEALED",
                        message=f"System Self-Healed Successfully!",
                        details=f"**Root Cause:**\n{root_cause}\n\n**Patched File:** `{patch_file}`\n\n**Recovery Log:**\n{recovery_logs}"
                    )
                else:
                    print("[DEFENDER] Failed to trigger restart via orchestrator.")
            except Exception as patch_err:
                print(f"[DEFENDER] Failed to apply patch: {patch_err}")
                await post_dashboard_log(
                    event_type="HEAL_FAILED",
                    message="Error occurred while applying SRE patch.",
                    details=str(patch_err)
                )
        else:
            print("[DEFENDER] Failed to parse patch or no patch returned by Gemini.")
            await post_dashboard_log(
                event_type="HEAL_FAILED",
                message="Gemini diagnostic report could not be parsed.",
                details=f"**Report Text:**\n{healing_md}"
            )
            
if __name__ == "__main__":
    asyncio.run(inspect_loop())
