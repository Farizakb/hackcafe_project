# 🎯 Chaos Nexus - Autonomous Multi-Agent Self-Healing System

## Project Overview

**Chaos Nexus** is an interactive, gamified self-healing system that demonstrates advanced Agentic AI capabilities. It features:

- **Saboteur Agent** (Chaos Injector) - Randomly corrupts the target application
- **Defender Agent** (SRE Self-Healer) - Autonomously detects and fixes failures using Gemini AI
- **Target Application** (FastAPI Microservice) - The system under protection
- **Orchestrator Dashboard** - Real-time visualization of the chaos game

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│         ORCHESTRATOR (main.py) - Port 8080                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │    Glassmorphic Real-Time Dashboard UI              │   │
│  │  - System Health Monitor                            │   │
│  │  - Chaos Attack History                             │   │
│  │  - Self-Healing Events Log                          │   │
│  │  - Target App Live Terminal                         │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────┬──────────────────────────┘
               │                  │
      ┌────────▼─────────┐  ┌──────▼──────────┐
      │  TARGET APP      │  │  SABOTEUR       │
      │  (Port 8000)     │  │  (Port 8001)    │
      │  - /health       │  │ - /trigger-chaos│
      │  - /users        │  │ - /chaos-history│
      │  - /metrics      │  └──────────────────┘
      └────────┬─────────┘
               │
      ┌────────▼─────────────────┐
      │  DEFENDER (Background)   │
      │  - Health Monitor Loop   │
      │  - Gemini AI Integration │
      │  - Auto-Patch Generator  │
      │  - File Restoration      │
      └──────────────────────────┘
```

---

## Prerequisites

- **Python 3.9+** installed
- **Google Gemini API Key** (set in `.env` file)
- **Docker & Docker Compose** (for containerized deployment)
- **Google Cloud Project** (for Cloud Run deployment)

---

## Local Setup

### 1. Install Dependencies

```bash

pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create or verify `.env` file:

```env
GEMINI_API_KEY="your_actual_gemini_key_here"
DB_FILE="users_db.json"
APP_ENV="production"
PORT=8000
DB_PORT=5432
```

### 3. Run Locally

```bash
# Terminal 1: Start the orchestrator (includes all sub-processes)
python main.py
```

This automatically starts:
- **Target App** on `http://localhost:8000`
- **Saboteur Agent** on `http://localhost:8001`
- **Defender Agent** (background loop)
- **Dashboard** on `http://localhost:8080`

### 4. Access the Dashboard

Open browser and navigate to:
```
http://localhost:8080
```

You'll see:
- 🛡️ **System Nodes Monitor** - Real-time health of all components
- 😈 **Chaos Saboteur Engine** - Button to trigger attacks
- 🤖 **SRE Defender Operations** - Live healing events
- 📟 **Target App Terminal** - Real-time stdout/stderr logs

---

## Testing Workflow

### Manual Testing

1. **Trigger Chaos Attack:**
   - Click **"⚡ Inject Dynamic Chaos Attack"** button
   - Observe saboteur attack type: syntax error, logical error, env corruption, or DB wipeout

2. **Watch Defender Heal:**
   - See the target app crash in the logs
   - Defender detects failure and calls Gemini
   - Gemini generates a patch
   - File is restored and process restarts
   - System returns to healthy state

3. **Monitor Metrics:**
   - Badge indicators show system state
   - "● System Secure" → "● Failure Detected" → "● System Secure"

### Programmatic Testing

```bash
# Trigger saboteur endpoint directly
curl -X POST http://localhost:8001/trigger-chaos

# Get chaos history
curl http://localhost:8001/chaos-history

# Check target app health
curl http://localhost:8000/health

# Get all users
curl http://localhost:8000/users

# Check orchestrator status
curl http://localhost:8080/status
```

---

## Docker Deployment

### Build Docker Image

```bash
docker build -t chaos-nexus:latest .
```

### Run with Docker Compose

```bash
docker-compose up --build
```

This exposes:
- Port `8080` - Orchestrator Dashboard
- Port `8000` - Target FastAPI Application
- Port `8001` - Chaos Saboteur Agent

```bash
# Access from host machine
http://localhost:8080  # Dashboard
```

---

## Google Cloud Deployment

### Prerequisites

1. **Create Google Cloud Project:**
   ```bash
   gcloud projects create chaos-nexus --name="Chaos Nexus Arena"
   gcloud config set project chaos-nexus
   ```

2. **Enable Required APIs:**
   ```bash
   gcloud services enable run.googleapis.com
   gcloud services enable aiplatform.googleapis.com
   ```

3. **Create Service Account:**
   ```bash
   gcloud iam service-accounts create chaos-nexus-sa \
     --display-name="Chaos Nexus Service Account"
   
   gcloud projects add-iam-policy-binding chaos-nexus \
     --member="serviceAccount:chaos-nexus-sa@chaos-nexus.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```

## Project Structure

```
hackcafe_project/
├── main.py                 # Orchestrator + Dashboard UI
├── target_app.py           # Target FastAPI application (port 8000)
├── saboteur_agent.py       # Chaos injection agent (port 8001)
├── defender_agent.py       # SRE self-healing agent
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Multi-container orchestration
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (GEMINI_API_KEY)
├── users_db.json           # Mock database
└── target_app.log          # Runtime logs

```

---

## Key Components

### 1. **target_app.py** (Port 8000)
- FastAPI microservice with intentional vulnerabilities
- **Routes:**
  - `GET /health` - Health check
  - `GET /users` - Returns user list from JSON DB
- **Vulnerabilities:**
  - JSON parsing errors
  - Missing database files
  - Invalid environment variables
  - Code syntax errors

### 2. **saboteur_agent.py** (Port 8001)
- Injects chaos into the system
- **Attack Methods:**
  - **Syntax Injection** - Breaks Python code
  - **Logical Errors** - Throws exceptions at runtime
  - **Env Corruption** - Sets invalid configuration
  - **DB Wipeout** - Corrupts JSON data
- **Endpoints:**
  - `GET/POST /trigger-chaos` - Execute random attack
  - `GET /chaos-history` - View past attacks

### 3. **defender_agent.py** (Background)
- Autonomous monitoring loop
- **Features:**
  - Polls `/health` and `/users` endpoints every 3 seconds
  - Detects failures (HTTP errors, timeouts, crashes)
  - Reads application logs and current source code
  - Calls Gemini 3.5 Flash with full context
  - Parses Markdown patch response
  - Applies patches to filesystem
  - Triggers orchestrator to restart target app
  - Sends healing events to dashboard

### 4. **main.py** (Port 8080)
- Central orchestrator and dashboard
- **Features:**
  - Spawns all child processes at startup
  - Graceful shutdown with process cleanup
  - Real-time health monitoring
  - Beautiful glassmorphic UI
  - WebSocket-style polling for live updates
  - Event logging system

---

## Troubleshooting

### Issue: "GEMINI_API_KEY not found"
**Solution:** Verify `.env` file exists and contains valid API key:
```bash
cat .env
```

### Issue: Defender not healing
**Solution:** Check Defender logs:
```bash
# Monitor defender in real-time
tail -f target_app.log
```

### Issue: Port already in use
**Solution:** Kill processes on ports 8000, 8001, 8080:
```bash
# Windows
netstat -ano | findstr :8080
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8080
kill -9 <PID>
```

### Issue: Docker build fails
**Solution:** Ensure `.env` file is in root directory and has GEMINI_API_KEY:
```bash
cp .env.example .env
# Edit .env with your actual key
```

---

## Performance Metrics

- **Failure Detection Latency:** ~3 seconds
- **Gemini AI Response Time:** ~5-10 seconds
- **Patch Application Time:** <1 second
- **Target App Restart Time:** ~2 seconds
- **Total Healing Time:** ~10-15 seconds

---

## Future Enhancements

- [ ] WebSocket support for true real-time dashboard updates
- [ ] Multiple simultaneous chaos attacks
- [ ] Attack intensity levels (mild, severe, critical)
- [ ] Custom attack templates
- [ ] Healing success rate metrics
- [ ] Cost analysis for cloud deployment
- [ ] Integration with Google Cloud Monitoring
- [ ] Alert notifications (Email, Slack, PagerDuty)

---

## License

MIT License - Feel free to use for educational and research purposes

---

## Contributing

This project demonstrates autonomous SRE capabilities using:
- **Agentic AI** - Defender makes independent decisions
- **LLM Integration** - Gemini for intelligent patching
- **Real-time Monitoring** - Dashboard visualization
- **Multi-process Orchestration** - Complex system coordination

Perfect for learning advanced Python, async patterns, and AI-driven DevOps!
