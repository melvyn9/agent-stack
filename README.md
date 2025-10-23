# Agent Stack — AWS Bedrock Multi-Agent System

This project creates a **multi-container agent framework** on AWS EC2 using **Docker Compose**.  
Each user gets their **own isolated container** that connects to **AWS Bedrock** (e.g., Titan Text Lite model) to handle AI-based chat requests.

---

## 1. Environment Setup

### EC2 Configuration
- **Instance type:** `t3.large` (2 vCPU, 8 GB RAM recommended)  
- **AMI:** Ubuntu 24.04 LTS (x86_64)  
- **Ports:** Allow **22 (SSH)** and optionally **7000 (API)**  
- **SSH in:**
  ```bash
  ssh -i <your-key.pem> ubuntu@<EC2_PUBLIC_IP>

## 2. System Setup on EC2
The following has already been installed on the instance. Only do this if starting from a brand new instance or if 5. Running the Stack does not work.
Install dependencies and tools:
```bash
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release unzip jq
```

Install Docker & Compose
```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
sudo systemctl enable docker
sudo systemctl start docker
```

Install AWS CLI
```bash
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip
unzip -q awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip
```

## 3. Repository Structure
```bash
agent-stack/
├─ agent/               # Template for user-specific agent containers
│  └─ agent.py          # Each agent handles user chat, tools, and Bedrock calls
│
├─ dispatcher/          # Central manager that routes requests and spawns user agents
│  └─ dispatcher.py     # Creates per-user containers and forwards chat requests
│
├─ .env                 # AWS credentials (temporary Educate keys)
├─ docker-compose.yml   # Service definitions for Dispatcher and Agent template
└─ README.md            # This documentation
```

## 4. Environment Variables
The .env file in the root directory stores temporary AWS Educate credentials. Go to https://ets-apps.ucsd.edu/individual/CSE291A_FA25_D00 and click "Generate API Keys (for CLI/scripting) for your own API keys.
```bash
AWS_ACCESS_KEY_ID= Your Access Key ID
AWS_SECRET_ACCESS_KEY= Your Secret Access Key
AWS_SESSION_TOKEN= Your Session Key
AWS_REGION=us-west-2
```

## 5. Running the Stack
Build and Start
```bash
cd ~/agent-stack
docker compose build
docker compose up -d
```

Check Service Health:
```bash
curl http://localhost:7000/healthz
# {"ok":true}
```

## 6. How Per-User Isolation Works
- The Dispatcher listens on port 7000 and spawns containers dynamically.
- When you send a request to /u/<user>/chat, a container named agent-<user> is launched.
- Each user’s container is:
    - Connected to the shared network agent-stack_agent_net
    - Given isolated environment variables (AWS keys, model ID, region)
    - Independent from other users

Check which containers are active:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
```

Example Output:
```bash
NAMES                          STATUS
agent-dispatcher               Up 2 minutes
agent-alice                    Up 1 minute
agent-bob                      Up 10 seconds
```
Each user = one isolated agent container.
Each session ID = a conversation thread inside that same container.

## 7. Sending Chat Requests
```bash
POST http://<EC2_PUBLIC_IP>:7000/u/{user}/chat?session_id={session_id}
```

Body:
```bash
{
  "message": "Explain why container isolation is useful"
}
```

Example Calls:
```bash
# User Alice
curl -X POST "http://localhost:7000/u/alice/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"/calc 2*(3+4)"}'

# User Bob
curl -X POST "http://localhost:7000/u/bob/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain why container isolation is useful"}'
```
### Parameters Explained

| **Parameter** | **Meaning** |
|----------------|-------------|
| `/u/{user}` | Creates or reuses container `agent-{user}` |
| `session_id` | Tracks conversation within the same container |
| `message` | Either `/calc`, `/search`, or free-form text for the LLM |

### Calling Different Users

Each unique **user** name creates (or reuses) a separate isolated container named `agent-{user}`.  
This ensures that every user runs in their **own environment**, with separate AWS credentials, memory, and model state.

**Example:**
```bash
# Create or reuse Alice's agent
curl -X POST "http://localhost:7000/u/alice/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello, what can you do?"}'

# Create or reuse Bob's agent (in a separate container)
curl -X POST "http://localhost:7000/u/bob/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain container isolation"}'
```

After these calls:
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
```

will show:
```bash
agent-dispatcher    Up 3 minutes
agent-alice         Up 1 minute
agent-bob           Up 20 seconds
```
Each container (agent-alice, agent-bob, etc.) is a fully isolated environment —
even though they share the same network, they cannot interfere with each other.

### Understanding session_id
The session_id parameter keeps track of conversation continuity within a single user’s container.
- Each new session_id starts a fresh conversation.
- Using the same session_id allows messages to be part of the same session context (for memory, if added later).

```bash
# Continuing the same session for Alice
curl -X POST "http://localhost:7000/u/alice/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"Remind me what container isolation means"}'

# Starting a new session for Alice
curl -X POST "http://localhost:7000/u/alice/chat?session_id=s2" \
  -H "Content-Type: application/json" \
  -d '{"message":"Summarize what you know about Docker networking"}'
```
Sessions are currently stateless (they don’t retain memory).
In later phases, session_id will link to Redis or another memory store so agents can “remember” previous messages.

### Example Success Output
```bash
curl -X POST "http://localhost:7000/u/bob/chat?session_id=s1" \
  -H "Content-Type: application/json" \
  -d '{"message":"Explain why container isolation is useful"}'

# Response
{"model":"amazon.titan-text-lite-v1",
 "answer":"Container isolation is useful because it separates applications..."}
```

## 8. Model Configuration
The system defaults to Amazon Titan Text Lite, which supports on-demand invocation.

These are all the models available to use on Bedrock
| **Category** | **Provider** | **Model ID(s)** | **Purpose / Notes** |
|---------------|--------------|-----------------|----------------------|
| **Text Generation** | **Amazon** | `amazon.titan-text-lite-v1`, `amazon.titan-text-express-v1`, `amazon.nova-pro-v1:0`, `amazon.nova-lite-v1:0`, `amazon.nova-micro-v1:0` | General-purpose LLMs for text generation and reasoning. Titan models support on-demand invocation. |
| **Image Generation & Editing** | **Stability AI** | `stability.stable-image-*`, `stability.sd3-5-large-v1:0`, `stability.stable-style-transfer-v1:0` | Image creation, recoloring, style transfer, and background removal. |
| **Text & Image Embeddings** | **Amazon** | `amazon.titan-embed-text-v1`, `amazon.titan-embed-text-v2:0`, `amazon.titan-embed-image-v1` | Converts text or images into dense vector representations for search and semantic tasks. |
| **Ranking & Retrieval** | **Amazon** | `amazon.rerank-v1:0` | Reranks document or passage lists for retrieval-augmented tasks. |
| **Embeddings & Multilingual Models** | **Cohere** | `cohere.embed-v4:0`, `cohere.embed-english-v3`, `cohere.embed-multilingual-v3`, `cohere.command-r-v1:0`, `cohere.command-r-plus-v1:0` | Text embeddings, multilingual understanding, and instruction-following models. |
| **Text Embedding (Legacy)** | **Amazon** | `amazon.titan-embed-g1-text-02` | Older generation Titan embedding model for backward compatibility. |
| **Image Tools (New Gen)** | **Amazon** | `amazon.titan-image-generator-v1`, `amazon.titan-image-generator-v2:0` | Generate and modify images using Titan’s image generation API. |

---

### Switching Models
To change the model your agent uses
In docker-compose.yml, update:
```bash
- BEDROCK_MODEL_ID=amazon.titan-text-lite-v1
```

to a different model
```bash
- BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
```

Then rebuild and restart the stack
```bash
docker compose down
docker compose up -d --build
```

Verify the model works
```bash
docker exec -it agent-bob bash
echo $BEDROCK_MODEL_ID
```
### Model Compatibility Notes
AWS Bedrock supports many different model providers (Amazon, Anthropic, Stability AI, Cohere, etc.),  
but **each provider expects a different input/output schema**.  
Simply changing the environment variable `BEDROCK_MODEL_ID` is **not always enough** —  
you may need to adjust the code in `agent/agent.py` depending on the model type.

### How Model Switching Works

Your agent determines which schema to use by checking the model prefix in `agent.py`:

```python
if mid.startswith("anthropic."):
    # Anthropic Claude schema
elif mid.startswith("amazon.titan-text"):
    # Titan Text schema
else:
    return f"Model family not yet supported in this demo"
```
If you switch to a different model family (for example, from a text model to an image model),
you’ll need to update the code so the JSON request matches that model’s API format.

## 9. High-Level Architecture
```bash
                 ┌──────────────────────────────────────────────┐
                 │                  Dispatcher                  │
                 │   (FastAPI) - manages per-user containers    │
                 │   Port 7000                                  │
                 └──────────────┬───────────────────────────────┘
                                │
     ┌──────────────────────────┼──────────────────────────┐
     │                          │                          │
┌──────────────┐         ┌──────────────┐          ┌──────────────┐
│ agent-alice  │         │ agent-bob    │          │ agent-charlie│
│ Port 8080    │         │ Port 8080    │          │ Port 8080    │
│ Bedrock API  │         │ Bedrock API  │          │ Bedrock API  │
└──────────────┘         └──────────────┘          └──────────────┘
       │                        │                         │
       ▼                        ▼                         ▼
      AWS                  AWS Bedrock                AWS Bedrock
   (Titan / Claude)       (LLM Models)               (Future models)
```
- Dispatcher: central manager. Handles routing, spawns agent containers.

- Agent Template: base container image cloned per user.
Each instance calls Bedrock independently.

- Network: all containers share a single Docker bridge network.
