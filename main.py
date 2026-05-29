import os
import sys
import json
import asyncio
import subprocess
import threading
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

# Load env file
load_dotenv()

app = FastAPI(title="Chaos Nexus - Orchestrator Dashboard", version="1.0.0")

# Global Process References
target_process = None
saboteur_process = None
defender_process = None

# SRE Logs & Healing Events stored in memory
sre_events = []

# Target app log buffer (instead of keeping file open)
target_log_buffer = []
LOG_BUFFER_MAX_SIZE = 500  # Keep last 500 lines

def append_target_log(line):
    """Append to in-memory log buffer without blocking file I/O."""
    global target_log_buffer
    target_log_buffer.append(line.rstrip('\n'))
    if len(target_log_buffer) > LOG_BUFFER_MAX_SIZE:
        target_log_buffer.pop(0)
    
    # Also write to disk asynchronously
    try:
        with open("target_app.log", "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception:
        pass  # Silently ignore disk write failures

class DefenderLog(BaseModel):
    event_type: str
    message: str
    details: str = ""

def read_stream(process, name):
    """Read process stdout/stderr line-by-line without blocking."""
    try:
        for line in process.stdout:
            decoded_line = line.decode('utf-8', errors='replace')
            append_target_log(decoded_line)
            print(f"[{name}] {decoded_line.rstrip()}")
    except Exception as e:
        print(f"[{name}] Stream read error: {e}")

@app.on_event("startup")
async def startup_event():
    """Spawns the target app, saboteur, and defender processes concurrently."""
    global target_process, saboteur_process, defender_process
    
    # 1. Start clean target_app.log
    with open("target_app.log", "w") as f:
        f.write("=== Chaos Nexus Target Application Log Initialized ===\n")
    append_target_log("=== Chaos Nexus Target Application Log Initialized ===\n")
            
    print("[ORCHESTRATOR] Spawning target_app.py on port 8000...")
    target_process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "target_app.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'}
    )
    
    # Read target process output in background thread
    def stream_target():
        try:
            for line in target_process.stdout:
                decoded_line = line.decode('utf-8', errors='replace')
                append_target_log(decoded_line)
        except Exception as e:
            print(f"[TARGET] Stream error: {e}")
    
    threading.Thread(target=stream_target, daemon=True).start()
    
    print("[ORCHESTRATOR] Spawning saboteur_agent.py on port 8001...")
    saboteur_process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "saboteur_agent.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'}
    )
    
    print("[ORCHESTRATOR] Spawning defender_agent.py...")
    defender_process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "defender_agent.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'}
    )

@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully terminates all child processes on exit."""
    global target_process, saboteur_process, defender_process
    print("[ORCHESTRATOR] Terminating all agent processes...")
    for proc, name in [(target_process, "Target"), (saboteur_process, "Saboteur"), (defender_process, "Defender")]:
        if proc:
            try:
                proc.terminate()
                await proc.wait()
                print(f"[ORCHESTRATOR] {name} process exited cleanly.")
            except Exception as e:
                print(f"[ORCHESTRATOR] Failed to terminate {name} process: {e}")

@app.post("/restart-target")
async def restart_target():
    """
    Exposes an endpoint for the SRE Defender to trigger target application restarts.
    """
    global target_process
    print("[ORCHESTRATOR] 🚨 Restart requested by self-healing agent!")
    
    if target_process:
        try:
            target_process.terminate()
            await asyncio.wait_for(target_process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            target_process.kill()
            print(f"[ORCHESTRATOR] Target process killed after timeout")
        except Exception as e:
            print(f"[ORCHESTRATOR] Error terminating target_app: {e}")
    
    # Add separator to log
    append_target_log("\n=== TARGET PROCESS RESTART ===\n")
    
    # Restart the target process
    target_process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "target_app.py",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, 'PYTHONUNBUFFERED': '1'}
    )
    
    # Read target process output in background thread
    def stream_target():
        try:
            for line in target_process.stdout:
                decoded_line = line.decode('utf-8', errors='replace')
                append_target_log(decoded_line)
        except Exception as e:
            print(f"[TARGET] Stream error: {e}")
    
    threading.Thread(target=stream_target, daemon=True).start()
    
    log_event = {
        "timestamp": asyncio.get_event_loop().time(),
        "event_type": "RESTART",
        "message": "Process reloaded successfully following patch deployment.",
        "details": "Target FastAPI process resurrected on port 8000."
    }
    sre_events.append(log_event)
    
    return JSONResponse(content={"status": "restarted"})

@app.post("/log-defender")
async def log_defender(log: DefenderLog):
    """Stores logs and notifications dispatched by the SRE Defender agent."""
    import time
    timestamp = time.strftime("%H:%M:%S")
    event = {
        "timestamp": timestamp,
        "event_type": log.event_type,
        "message": log.message,
        "details": log.details
    }
    sre_events.append(event)
    return {"status": "logged"}

@app.get("/status")
async def get_status():
    """Provides a JSON snapshot of the system state to drive the dashboard UI."""
    target_up = False
    target_health = "Offline"
    
    # Check if target app is running and responding
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:8000/health", timeout=1.0)
            if resp.status_code == 200:
                target_up = True
                target_health = "Healthy"
            else:
                target_health = f"Unhealthy (Status {resp.status_code})"
    except Exception:
        target_health = "Offline/Crashed"

    # Use in-memory log buffer instead of reading from disk
    target_logs = "\n".join(target_log_buffer[-30:]) if target_log_buffer else "No log data."

    return JSONResponse(content={
        "target_app": {
            "health": target_health,
            "is_up": target_up,
            "port": 8000
        },
        "saboteur": {
            "is_up": saboteur_process is not None and saboteur_process.returncode is None,
            "port": 8001
        },
        "defender": {
            "is_up": defender_process is not None and defender_process.returncode is None
        },
        "sre_events": sre_events,
        "target_logs": target_logs
    })

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Renders a state-of-the-art SRE Control Dashboard with Premium Glassmorphism styling."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Chaos Nexus - SRE Control Deck</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <style>
            :root {
                --bg-color: #0b0c15;
                --card-bg: rgba(20, 22, 39, 0.65);
                --card-border: rgba(255, 255, 255, 0.08);
                --text-main: #f3f4f6;
                --text-muted: #9ca3af;
                
                --neon-cyan: #06b6d4;
                --neon-cyan-glow: rgba(6, 182, 212, 0.3);
                --neon-green: #10b981;
                --neon-green-glow: rgba(16, 185, 129, 0.3);
                --neon-red: #f43f5e;
                --neon-red-glow: rgba(244, 63, 94, 0.3);
                --neon-purple: #a855f7;
            }
            
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }
            
            body {
                font-family: 'Outfit', sans-serif;
                background-color: var(--bg-color);
                color: var(--text-main);
                overflow-x: hidden;
                background-image: 
                    radial-gradient(at 10% 20%, rgba(168, 85, 247, 0.15) 0px, transparent 50%),
                    radial-gradient(at 90% 80%, rgba(6, 182, 212, 0.15) 0px, transparent 50%);
                background-attachment: fixed;
                min-height: 100vh;
                padding: 2rem;
            }

            header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 2rem;
                padding-bottom: 1rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            h1 {
                font-size: 2.5rem;
                font-weight: 800;
                background: linear-gradient(135deg, #06b6d4 0%, #a855f7 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                display: flex;
                align-items: center;
                gap: 0.75rem;
            }

            h1 span {
                font-size: 1rem;
                font-weight: 400;
                background: rgba(255, 255, 255, 0.1);
                color: var(--neon-cyan);
                padding: 0.2rem 0.6rem;
                border-radius: 9999px;
                border: 1px solid var(--neon-cyan);
            }

            .grid {
                display: grid;
                grid-template-columns: 1fr 1.2fr;
                gap: 1.5rem;
                margin-bottom: 1.5rem;
            }

            @media(max-width: 1024px) {
                .grid {
                    grid-template-columns: 1fr;
                }
            }

            .card {
                background: var(--card-bg);
                backdrop-filter: blur(16px);
                border: 1px solid var(--card-border);
                border-radius: 16px;
                padding: 1.5rem;
                box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
                display: flex;
                flex-direction: column;
                transition: transform 0.2s ease, border-color 0.2s ease;
            }

            .card:hover {
                border-color: rgba(255, 255, 255, 0.15);
            }

            .card-title {
                font-size: 1.25rem;
                font-weight: 600;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                padding-bottom: 0.5rem;
            }

            /* Health Badges */
            .badge {
                padding: 0.25rem 0.75rem;
                border-radius: 9999px;
                font-size: 0.85rem;
                font-weight: 600;
                display: inline-flex;
                align-items: center;
                gap: 0.35rem;
            }

            .badge-success {
                background-color: rgba(16, 185, 129, 0.15);
                color: var(--neon-green);
                border: 1px solid var(--neon-green);
                box-shadow: 0 0 10px var(--neon-green-glow);
            }

            .badge-danger {
                background-color: rgba(244, 63, 94, 0.15);
                color: var(--neon-red);
                border: 1px solid var(--neon-red);
                box-shadow: 0 0 10px var(--neon-red-glow);
            }

            .status-row {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 0.75rem 0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            }

            .btn {
                background: linear-gradient(135deg, var(--neon-red) 0%, #be123c 100%);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 0.75rem 1.5rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s ease;
                box-shadow: 0 4px 15px rgba(244, 63, 94, 0.4);
                display: inline-flex;
                justify-content: center;
                align-items: center;
                gap: 0.5rem;
            }

            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(244, 63, 94, 0.6);
            }

            .btn:active {
                transform: translateY(0);
            }

            /* Log Terminals */
            .terminal {
                background: #05060b;
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 8px;
                padding: 1rem;
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85rem;
                color: #22d3ee;
                height: 300px;
                overflow-y: auto;
                white-space: pre-wrap;
                box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
            }

            .sre-terminal {
                height: 400px;
                color: #e5e7eb;
            }

            .log-entry {
                margin-bottom: 0.75rem;
                border-left: 3px solid #6b7280;
                padding-left: 0.5rem;
            }

            .log-entry.DISPATCH {
                border-left-color: var(--neon-cyan);
            }

            .log-entry.HEALED {
                border-left-color: var(--neon-green);
                background: rgba(16, 185, 129, 0.05);
            }

            .log-entry.HEAL_FAILED {
                border-left-color: var(--neon-red);
                background: rgba(244, 63, 94, 0.05);
            }

            .log-entry.RESTART {
                border-left-color: var(--neon-purple);
            }

            .log-time {
                color: var(--text-muted);
                font-size: 0.75rem;
                margin-bottom: 0.2rem;
            }

            .log-title {
                font-weight: 700;
                color: #f3f4f6;
            }

            .log-details {
                font-size: 0.8rem;
                color: #cbd5e1;
                margin-top: 0.25rem;
                white-space: pre-wrap;
            }

            /* Loading spinner overlay */
            .overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(11, 12, 21, 0.8);
                display: none;
                justify-content: center;
                align-items: center;
                z-index: 9999;
                backdrop-filter: blur(8px);
            }

            .spinner {
                width: 50px;
                height: 50px;
                border: 4px solid rgba(6, 182, 212, 0.1);
                border-left-color: var(--neon-cyan);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }

            @keyframes spin {
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div id="loadingOverlay" class="overlay">
            <div style="text-align: center;">
                <div class="spinner"></div>
                <p style="margin-top: 1rem; font-weight: 600; color: var(--neon-cyan);">Injecting Sabotage Attack...</p>
            </div>
        </div>

        <header>
            <h1>Chaos Nexus <span>Multi-Agent Live Arena</span></h1>
            <div id="systemPulse" class="badge badge-success">● System Secure</div>
        </header>

        <div class="grid">
            <!-- LEFT PANEL: SYSTEM HEALTH & SABOTEUR CONTROL -->
            <div style="display: flex; flex-direction: column; gap: 1.5rem;">
                <div class="card">
                    <div class="card-title">🛡️ System Nodes Monitor</div>
                    <div class="status-row">
                        <span>Target Microservice (Port 8000):</span>
                        <span id="targetHealthBadge" class="badge">Checking...</span>
                    </div>
                    <div class="status-row">
                        <span>Chaos Saboteur (Port 8001):</span>
                        <span id="saboteurHealthBadge" class="badge">Checking...</span>
                    </div>
                    <div class="status-row">
                        <span>SRE Defender Agent (Background):</span>
                        <span id="defenderHealthBadge" class="badge">Checking...</span>
                    </div>
                </div>

                <div class="card">
                    <div class="card-title">😈 Chaos Saboteur Engine</div>
                    <p style="color: var(--text-muted); margin-bottom: 1.5rem; font-size: 0.95rem;">
                        Trigger the Saboteur Agent. It will randomly inject logical code failures, syntax-breaking bugs, env var corruption, or wipe the database structure!
                    </p>
                    <button class="btn" onclick="triggerSabotage()">
                        ⚡ Inject Dynamic Chaos Attack
                    </button>
                    
                    <h4 style="margin-top: 1.5rem; margin-bottom: 0.5rem; font-size: 0.95rem; font-weight: 600;">Chaos Attack History:</h4>
                    <div id="chaosHistoryTerminal" class="terminal" style="height: 140px; color: #f43f5e; font-size: 0.8rem;">
                        No attacks recorded yet.
                    </div>
                </div>
            </div>

            <!-- RIGHT PANEL: SRE DEFENDER REALTIME LOGS -->
            <div class="card">
                <div class="card-title">🤖 SRE Defender Self-Healing Operations</div>
                <div id="sreLogs" class="terminal sre-terminal">
                    Waiting for events...
                </div>
            </div>
        </div>

        <!-- ROW: TARGET RUNTIME TERMINAL -->
        <div class="card">
            <div class="card-title">📟 Target App Terminal stdout/stderr</div>
            <div id="targetTerminal" class="terminal" style="color: #10b981;">
                Initializing console streams...
            </div>
        </div>

        <script>
            async function triggerSabotage() {
                const overlay = document.getElementById("loadingOverlay");
                overlay.style.display = "flex";
                try {
                    const response = await fetch("http://localhost:8001/trigger-chaos");
                    const data = await response.json();
                    console.log("Chaos Injected:", data);
                } catch (error) {
                    console.error("Failed to inject chaos:", error);
                } finally {
                    // Quick timeout to let system register state
                    setTimeout(() => {
                        overlay.style.display = "none";
                        updateState();
                    }, 1000);
                }
            }

            async function updateState() {
                try {
                    const response = await fetch("/status");
                    const state = await response.json();
                    
                    // Update Target App Badge
                    const targetBadge = document.getElementById("targetHealthBadge");
                    if (state.target_app.health === "Healthy") {
                        targetBadge.className = "badge badge-success";
                        targetBadge.innerText = "● Healthy";
                        document.getElementById("systemPulse").className = "badge badge-success";
                        document.getElementById("systemPulse").innerText = "● System Secure";
                    } else {
                        targetBadge.className = "badge badge-danger";
                        targetBadge.innerText = "● " + state.target_app.health;
                        document.getElementById("systemPulse").className = "badge badge-danger";
                        document.getElementById("systemPulse").innerText = "● Failure Detected";
                    }

                    // Update Saboteur Badge
                    const saboteurBadge = document.getElementById("saboteurHealthBadge");
                    if (state.saboteur.is_up) {
                        saboteurBadge.className = "badge badge-success";
                        saboteurBadge.innerText = "● Online";
                    } else {
                        saboteurBadge.className = "badge badge-danger";
                        saboteurBadge.innerText = "● Offline";
                    }

                    // Update Defender Badge
                    const defenderBadge = document.getElementById("defenderHealthBadge");
                    if (state.defender.is_up) {
                        defenderBadge.className = "badge badge-success";
                        defenderBadge.innerText = "● Active Inspection";
                    } else {
                        defenderBadge.className = "badge badge-danger";
                        defenderBadge.innerText = "● Deactivated";
                    }

                    // Update SRE healing logs
                    const sreContainer = document.getElementById("sreLogs");
                    if (state.sre_events.length > 0) {
                        sreContainer.innerHTML = state.sre_events.map(event => {
                            let badgeStyle = "DISPATCH";
                            if (event.event_type === "HEALED") badgeStyle = "HEALED";
                            if (event.event_type === "HEAL_FAILED") badgeStyle = "HEAL_FAILED";
                            if (event.event_type === "RESTART") badgeStyle = "RESTART";
                            
                            return `
                                <div class="log-entry ${badgeStyle}">
                                    <div class="log-time">[${event.timestamp}] EVENT TYPE: ${event.event_type}</div>
                                    <div class="log-title">${event.message}</div>
                                    ${event.details ? `<div class="log-details">${event.details}</div>` : ""}
                                </div>
                            `;
                        }).join("");
                    } else {
                        sreContainer.innerHTML = "<div style='color: var(--text-muted);'>No self-healing events yet. Monitoring target nodes...</div>";
                    }

                    // Update Target App log terminal
                    const term = document.getElementById("targetTerminal");
                    term.innerText = state.target_logs;
                    // Auto-scroll terminal to bottom
                    term.scrollTop = term.scrollHeight;

                } catch (error) {
                    console.error("Failed updating state:", error);
                }
            }

            async function updateChaosHistory() {
                try {
                    const response = await fetch("http://localhost:8001/chaos-history");
                    if (response.ok) {
                        const history = await response.json();
                        const histTerm = document.getElementById("chaosHistoryTerminal");
                        if (history.length > 0) {
                            histTerm.innerHTML = history.map(attack => {
                                return `[${attack.timestamp}] ATTACK #${attack.id} - METHOD: ${attack.method.toUpperCase()}\n> ${attack.details}\n\n`;
                            }).join("");
                            histTerm.scrollTop = histTerm.scrollHeight;
                        }
                    }
                } catch(e) {
                    console.error("Failed to load chaos history:", e);
                }
            }

            // Real-time loop
            setInterval(updateState, 1000);
            setInterval(updateChaosHistory, 1000);
            
            // Initial call
            updateState();
            updateChaosHistory();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    # Start Central Control Deck on port 8080
    uvicorn.run("main:app", host="0.0.0.0", port=8080, log_level="info", reload=False)
