import os
import json
from typing import Dict, Any
from fastapi import FastAPI, Query, HTTPException, Body
from pydantic import BaseModel
import boto3
import httpx
from react_agent import LangGraphReActAgent

app = FastAPI(title="Per-User Agent")

# Initialize agent once at startup
agent = None

@app.on_event("startup")
async def startup_event():
    """Initialize the agent on startup"""
    global agent
    try:
        agent = LangGraphReActAgent()
    except Exception as e:
        print(f"Error initializing agent: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global agent
    agent = None


class ChatRequest(BaseModel):
    """Request body for chat endpoint"""
    message: str


class AgentRequest(BaseModel):
    """Request body for agent endpoint"""
    message: str


@app.post("/chat")
async def chat(
    user_id: str = Query(..., description="User ID"),
    session_id: str = Query(..., description="Session ID"),
    request: ChatRequest = Body(...),
) -> Dict[str, Any]:
    """Simple chat endpoint without agent tools"""
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        # agent.chat() should be synchronous, not async
        answer = agent.chat(request.message)
        return {"result": answer, "user_id": user_id, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.post("/agent")
async def run_agent(
    user_id: str = Query(..., description="User ID"),
    session_id: str = Query(..., description="Session ID"),
    request: AgentRequest = Body(...),
) -> Dict[str, Any]:
    """Run the ReAct agent with tools"""
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    try:
        thread_id = f"{user_id}_{session_id}" if user_id and session_id else "default"

        response = agent.run(message=request.message, thread_id=thread_id)
        return {
            "result": response,
            "user_id": user_id,
            "session_id": session_id,
            "thread_id": thread_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint"""
    return {"status": "ok", "agent_ready": agent is not None}


@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint"""
    return {"message": "Per-User Agent API", "docs": "/docs"}
