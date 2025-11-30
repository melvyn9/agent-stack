import os, time, httpx, docker
from fastapi import FastAPI, Request, HTTPException

AGENT_IMAGE = os.getenv("AGENT_IMAGE","agent-template:latest")
NETWORK_NAME = os.getenv("NETWORK_NAME","agent_net")
BEDROCK_REGION = os.getenv("AWS_REGION", "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.titan-text-lite-v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

app = FastAPI(title="Dispatcher")

def client(): return docker.from_env()

def ensure_network(c):
    nets={n.name for n in c.networks.list()}
    if NETWORK_NAME not in nets: c.networks.create(NETWORK_NAME,driver="bridge")

def ensure_agent(c,user):
    name=f"agent-{user}"
    ensure_network(c)
    try:
        cont=c.containers.get(name)
        if cont.status!="running": cont.start()
        return name
    except docker.errors.NotFound:
        env = {
                "BEDROCK_REGION": BEDROCK_REGION,
                "BEDROCK_MODEL_ID": BEDROCK_MODEL_ID,
                "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                "AWS_REGION": os.getenv("AWS_REGION", "us-west-2"),
                "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", ""),
                "SERPAPI_API_KEY": os.getenv("SERPAPI_API_KEY", ""),
                "PINECONE_API_KEY": os.getenv("PINECONE_API_KEY", "")
            }
        cont=c.containers.run(AGENT_IMAGE,name=name,detach=True,environment=env,network=NETWORK_NAME)
        # Wait longer and retry to ensure container is ready
        time.sleep(5)
        return name

async def proxy(user,sess,payload):
    c=client()
    name=ensure_agent(c,user)
    url=f"http://{name}:8080/agent"
    
    # Retry logic for new containers
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=60) as cli:
                r=await cli.post(url,params={"user_id":user,"session_id":sess},json=payload)
                r.raise_for_status()
                return r.json()
        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
                continue
            else:
                raise

@app.post("/u/{user}/chat")
async def route(user:str,request:Request):
    sess=request.query_params.get("session_id")
    if not sess: raise HTTPException(400,"missing session_id")
    payload=await request.json()
    try: return await proxy(user,sess,payload)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/healthz")
def health(): return {"ok":True}
