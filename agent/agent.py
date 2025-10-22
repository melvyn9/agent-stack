import os, json
from fastapi import FastAPI, Query, HTTPException
import boto3, httpx

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.titan-text-lite-v1")

app = FastAPI(title="Per-User Agent")

def bedrock_client():
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

async def bedrock_chat(prompt: str):
    """
    Calls Bedrock with the correct schema depending on model family.
    - Anthropic Claude (messages API over invoke_model)
    - Amazon Titan Text (inputText / textGenerationConfig)
    """
    client = bedrock_client()

    mid = BEDROCK_MODEL_ID.lower()

    # ---- Anthropic (Claude) path ----
    if mid.startswith("anthropic."):
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
        resp = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        data = json.loads(resp["body"].read())
        parts = data.get("content", [])
        txt = "".join([p.get("text", "") for p in parts if p.get("type") == "text"]).strip()
        return txt if txt else "(no text returned)"

    # ---- Amazon Titan Text path ----
    if mid.startswith("amazon.titan-text"):
        body = {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 256,
                "temperature": 0.7,
                "topP": 0.9,
                "stopSequences": []
            }
        }
        resp = client.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        data = json.loads(resp["body"].read())
        # Titan returns: {"results": [{"outputText": "...", ...}, ...]}
        results = data.get("results", [])
        if results and "outputText" in results[0]:
            return results[0]["outputText"].strip()
        return "(no text returned)"

    # ---- Fallback for other providers/models (basic attempt) ----
    # You can extend this with more branches (Nova, Qwen, etc.)
    return f"Model family not yet supported in this demo: {BEDROCK_MODEL_ID}"

async def tool_calc(expr: str):
    try:
        return str(eval(expr, {"__builtins__": {}}))
    except Exception as e:
        return f"Calc error: {e}"

async def tool_search(q: str):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://duckduckgo.com/html", params={"q": q})
        return r.text[:500]

@app.post("/chat")
async def chat(user_id: str = Query(...), session_id: str = Query(...), payload: dict = {}):
    msg = payload.get("message","")
    if not msg: raise HTTPException(status_code=400, detail="Missing message")
    if msg.startswith("/calc "):
        res = await tool_calc(msg[6:])
        return {"tool":"calc","result":res}
    if msg.startswith("/search "):
        res = await tool_search(msg[8:])
        return {"tool":"search","result":res}
    answer = await bedrock_chat(msg)
    return {"model":BEDROCK_MODEL_ID,"answer":answer}

@app.get("/healthz")
def healthz(): return {"ok":True}
