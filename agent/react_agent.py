from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.language_models.base import BaseLanguageModel
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage

from mem0 import MemoryClient
from typing import List, Dict, Any, Optional, Union
import os
import json
import re
from mem0 import Memory
import redis


# Import our custom tools
from tools.calculator import evaluate_expression
from tools.web_search_content import search_and_fetch_content, fetch_web_content
from tools.file_reader import read_local_file
from tools.reddit_search import search_reddit
from llm import BedRockChatModel
# from langchain_aws import ChatBedrockConverse
import traceback
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0")

@tool
def calculator(expression: str) -> str:
    """Evaluate mathematical expressions safely.
    
    Args:
        expression: A mathematical expression to evaluate (e.g., "2 + 3 * 4")
    
    Returns:
        The result of the mathematical expression or an error message
    """
    result = evaluate_expression(expression)
    return str(result)


@tool
def search_web_with_content(query: str, max_results: int = 3, content_per_page: int = 3000) -> str:
    """Search the web and get actual content from top results.

    This tool searches the web and automatically fetches the actual text content
    from the top search results, providing you with the information you need
    without having to make separate fetch requests.

    Args:
        query: The search query
        max_results: Maximum number of search results to fetch content from (default: 3)
        content_per_page: Maximum characters to fetch per webpage (default: 3000)

    Returns:
        Formatted string with search results and their actual webpage content
    """
    return search_and_fetch_content(query, max_results, content_per_page)

@tool
def fetch_web_page(url: str, max_chars: int = 5000) -> str:
    """Fetch content from a web page.

    Args:
        url: The URL of the web page to fetch
        max_chars: Maximum number of characters to return (default: 5000)

    Returns:
        The text content of the web page or an error message
    """
    return fetch_web_content(url, max_chars)

@tool
def read_file(file_path: str, max_chars: int = 10000) -> str:
    """Read content from a local file on the system.

    Use this tool to read text files, code files, or any text-based documents.

    Args:
        file_path: Path to the file to read (absolute or relative path)
        max_chars: Maximum number of characters to return (default: 10000)

    Returns:
        The content of the file or an error message if the file cannot be read
    """
    return read_local_file(file_path, max_chars)


@tool
def reddit_search(query: str, subreddit: Optional[str] = None, max_results: int = 5, sort: str = "relevance") -> str:
    """Search Reddit posts and get actual post content.

    Use this to find discussions, opinions, and information from Reddit communities.

    Args:
        query: The search query
        subreddit: Optional subreddit name to search within (e.g., "python", "programming")
        max_results: Maximum number of results to return (default: 5)
        sort: Sort method - "relevance", "hot", "top", "new", "comments" (default: "relevance")

    Returns:
        Formatted string with Reddit posts including titles, scores, authors, and content
    """
    return search_reddit(query, subreddit, max_results, sort)



class LangGraphReActAgent:
    def __init__(
        self, 
        use_memory: bool = False, 
        **model_kwargs: Any
    ):
        """Initialize the LangGraph ReAct agent.
        
        Args:
            use_memory: Whether to use memory/checkpointing
            **model_kwargs: Additional arguments for the model
        """
        self.use_memory = use_memory
        # self.model = ChatBedrockConverse(model_id=BEDROCK_MODEL_ID, region_name=BEDROCK_REGION)
        self.model = BedRockChatModel()
        # self.model = ChatOpenAI(model_name="gpt-3.5-turbo-0125")
        
        # Define tools list
        self.tools = [
            calculator, 
            search_web_with_content, 
            read_file, 
            reddit_search, 
            fetch_web_page
        ]
        
        # Bind tools to the model so it knows about them
        # self.model_with_tools = self.model.bind_tools(self.tools)

        # Initialize checkpointer for memory
        self.checkpointer = None
        
        # Create the ReAct agent with our tools
        self.agent = create_react_agent(
            self.model,
            self.tools,
            checkpointer=self.checkpointer,
        )
        # self.mem = MemoryClient()
        config = {
            "vector_store": {
                "provider": "pinecone",
                "config": {
                    # Provider-specific settings go here
                    "collection_name": "291new",
                    "embedding_model_dims": 1536,
                    "api_key": os.getenv("PINECONE_API_KEY", ""),
                    "serverless_config": {
                        "cloud": "aws",
                        "region": "us-east-1"
                    },
                    "metric": "cosine"
                }
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "model": "gpt-3.5-turbo-0125",
                }
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small",
                    "embedding_dims": 1536
                }
            }
        }
        # Initialize Mem0 for LTM
        self.mem = Memory.from_config(config)
        # Initialize Redis for STM
        self.redis = redis.Redis(
                        host=os.getenv("REDIS_HOST", "agent-redis"),
                        port=int(os.getenv("REDIS_PORT", 6379)),
                        decode_responses=True
                    )

    def extract_memories_from_output(self, text: str):
        """
        Expect the agent to output:
        memory: ["fact1", "fact2", ...]
        """
        match = re.search(r"memory\s*:\s*(\[.*?\])", text, re.DOTALL)
        if not match:
            return []
        try:
            return json.loads(match.group(1))
        except Exception:
            return []
        

    # Redis Functions for STM
    def load_stm(self, thread_id):
        key = f"session:{thread_id}:history"
        raw = self.redis.lrange(key, 0, -1)
        return [json.loads(item) for item in raw]

    def store_stm(
        self,
        thread_id,
        role,
        text,
        window=5,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        share: bool = False,
        shared_with: Optional[List[str]] = None,
    ):
        key = f"session:{thread_id}:history"
        payload = json.dumps({"role": role, "text": text})

        # Push new STM message
        self.redis.rpush(key, payload)

        # If STM length exceeds window, migrate oldest pair to Mem0
        current_len = self.redis.llen(key)

        if current_len > window:
            # Pop oldest → first of pair
            first_raw = self.redis.lpop(key)
            first = json.loads(first_raw)

            # Peek next message (do NOT pop unless it's assistant)
            next_raw = self.redis.lindex(key, 0)
            if next_raw:
                next_msg = json.loads(next_raw)
            else:
                next_msg = None

            # Only pop and store pair if it is human→assistant
            if first["role"] == "human" and next_msg and next_msg["role"] == "assistant":
                # Pop the assistant message now that we know it's paired
                second_raw = self.redis.lpop(key)
                second = json.loads(second_raw)

                resolved_user, resolved_session = user_id, session_id
                if not resolved_user or not resolved_session:
                    resolved_user, resolved_session = thread_id.split("_", 1)

                mem_item = f"Question:{first['text']}, Agent Answer:{second['text']}"
                self._add_memory_for_users(
                    mem_item=mem_item,
                    owner_user_id=resolved_user,
                    session_id=resolved_session,
                    share=share,
                    shared_with=shared_with or [],
                    source="stm_eviction",
                )


        # Ensure STM keeps only the last `window` entries
        self.redis.ltrim(key, -window, -1)

    # End of Redis Functions for STM

    def _add_memory_for_users(
        self,
        mem_item: str,
        owner_user_id: str,
        session_id: Optional[str],
        share: bool,
        shared_with: List[str],
        source: str,
    ):
        """Store memory for owner and optionally shared recipients."""
        targets = [
            {
                "user_id": owner_user_id,
                "run_id": session_id,
                "visibility": "private" if not share else "shared",
            }
        ]

        if share and shared_with:
            for target in shared_with:
                targets.append(
                    {
                        "user_id": target,
                        "run_id": None,  # make shared memories available across sessions
                        "visibility": "shared",
                    }
                )

        metadata = {
            "owner": owner_user_id,
            "visibility": "shared" if share else "private",
            "shared_with": shared_with,
            "source": source,
        }

        for target in targets:
            try:
                # Skip duplicate entries for same user/visibility/memory text
                existing = self._search_memories(
                    query=mem_item,
                    user_id=target["user_id"],
                    run_id=target["run_id"],
                    visibility_filter=target["visibility"],
                    limit=1,
                )
                if existing:
                    continue
                self.mem.add(
                    messages=mem_item,
                    user_id=target["user_id"],
                    run_id=target["run_id"],
                    metadata={**metadata, "visibility": target["visibility"]},
                )
            except Exception as e:
                print(f"Error adding memory for user {target['user_id']}: {e}")

    def _search_memories(
        self,
        query: str,
        user_id: str,
        run_id: Optional[str],
        visibility_filter: Optional[str] = None,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search Mem0 with optional visibility filtering."""
        try:
            retrieved = self.mem.search(
                query=query,
                user_id=user_id,
                run_id=run_id,
                limit=limit,
            )
            results = retrieved.get("results", []) if retrieved else []
            if visibility_filter:
                results = [
                    r
                    for r in results
                    if r.get("metadata", {}).get("visibility") == visibility_filter
                ]
            return results
        except Exception as e:
            print(f"Error searching memories: {e}")
            return []

    def run(
        self,
        message: str,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        share: bool = False,
        shared_with: Optional[List[str]] = None,
    ) -> dict:
        """Run the agent with a message.

        Args:
            message: The user message
            thread_id: Unique identifier for the conversation thread
            system_prompt: Optional system prompt to override default behavior
            share: Whether to mark new memories as shared
            shared_with: List of user IDs allowed to access the shared memory

        Returns:
            The agent's response or error information
        """
        try:
            user_id, session_id = thread_id.split("_", 1) if thread_id else ("default_user", "default_session")
            
            # Retrieve relevant memory
            private_hits = self._search_memories(
                query=message,
                user_id=user_id,
                run_id=session_id,
                visibility_filter=None,
                limit=3,
            )
            shared_hits = self._search_memories(
                query=message,
                user_id=user_id,
                run_id=None,
                visibility_filter="shared",
                limit=3,
            )
            all_hits = private_hits + [h for h in shared_hits if h not in private_hits]
            print("Retrieved memory:", all_hits)
            
            # Load Redis short-term memory
            stm_history = self.load_stm(thread_id)
            stm_block = "\n".join(
                f"{item['role']}: {item['text']}"
                for item in stm_history
            ) or "No recent short-term memory."
            stm_strings = {
                f"Question:{item['text']}"
                for item in stm_history
                if item["role"] == "human"
            } | {
                f"Agent Answer:{item['text']}"
                for item in stm_history
                if item["role"] == "assistant"
            }

            if all_hits:
                formatted_hits = []
                for item in all_hits:
                    meta = item.get("metadata", {}) if isinstance(item, dict) else {}
                    visibility = meta.get("visibility", "private")
                    owner = meta.get("owner", user_id)
                    shared_marker = f"[{visibility} from {owner}]" if visibility == "shared" else "[private]"
                    mem_text = item.get("memory", "")
                    if mem_text in stm_strings:
                        continue
                    formatted_hits.append(f"- {shared_marker} {mem_text}")
                memory_block = "\n".join(formatted_hits) if formatted_hits else "No relevant memory retrieved."
            else:
                memory_block = "No relevant memory retrieved."
            memory_prefix = f"""
                            You are a ReAct agent with semantic memory.

                            Here are memories relevant to the user's message.
                            Use them *only if relevant*:
                            ### Short-Term Memory
                            {stm_block}
                            --- Retrieved Memory ---
                            {memory_block}
                            ------------------------
                            """

            config = {"configurable": {"thread_id": thread_id or "default"}}

            # Prepare messages
            messages = []
            if system_prompt:
                messages.append(("system", memory_prefix + system_prompt))
            else:
                messages.append(("system", memory_prefix))
            messages.append(("human", message))

            # Invoke the agent
            response = self.agent.invoke({"messages": messages}, config=config)

            # Extract final text depending on type
            final_text = ""
            if isinstance(response, ChatResult):
                # Use the last generation's message content
                if response.generations:
                    final_text = response.generations[-1].message.content
            elif isinstance(response, dict):
                if "messages" in response and response["messages"]:
                    final_text = response["messages"][-1].content
                else:
                    # fallback for older style response
                    final_text = response.get("output", "") or str(response)
            else:
                final_text = str(response)

            print("Agent response:", final_text)
            reasoning_part = None
            
            if "<reasoning>" in final_text:
                reasoning_part = final_text.split("<reasoning>")[1].split("</reasoning>")[0]
                final_text = final_text.replace(f"<reasoning>{reasoning_part}</reasoning>", "").strip()

            # Store STM (LTM handled inside store_stm overflow logic)
            self.store_stm(
                thread_id,
                "human",
                message,
                user_id=user_id,
                session_id=session_id,
                share=share,
                shared_with=shared_with or [],
            )
            self.store_stm(
                thread_id,
                "assistant",
                final_text,
                user_id=user_id,
                session_id=session_id,
                share=share,
                shared_with=shared_with or [],
            )
            # Immediately add to LTM for sharing even if STM window not exceeded
            if share:
                try:
                    mem_item = f"Question:{message}, Agent Answer:{final_text}"
                    self._add_memory_for_users(
                        mem_item=mem_item,
                        owner_user_id=user_id,
                        session_id=session_id,
                        share=share,
                        shared_with=shared_with or [],
                        source="immediate_share",
                    )
                except Exception as e:
                    print(f"Error sharing immediate memory: {e}")
            return {
                "response_text": final_text,
                "reasoning": reasoning_part,
                # "raw_response": response
            }

        except Exception as e:
            print("Error running agent:")
            print(str(e))
            traceback.print_exc()
            return {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
    def chat(self, message: str):
        return self.model.invoke(message)
