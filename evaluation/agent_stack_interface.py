"""
AgentInterface for agent-stack (LangGraph ReAct Agent on EC2)

This interface connects to the deployed agent-stack system running on EC2.
API: http://52.41.146.47:7000/u/{user}/agent?session_id={session_id}
"""

import requests
import json
from typing import Dict, List, Any
from datetime import datetime


class AgentStackInterface:
    """Interface to communicate with the deployed agent-stack system"""

    def __init__(self, base_url: str = "http://52.27.245.205:7000"):
        """
        Initialize connection to agent-stack

        Args:
            base_url: Base URL of the dispatcher service
        """
        self.base_url = base_url.rstrip('/')
        self.current_user_id = None
        self.current_session_id = None
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})

        # Test connection
        try:
            health = self.session.get(f"{self.base_url}/healthz", timeout=5)
            health.raise_for_status()
            print(f"[OK] Connected to agent-stack at {self.base_url}")
        except Exception as e:
            print(f"[!] Warning: Could not connect to agent-stack: {e}")
            print(f"  Make sure agent is running: docker compose up -d")

    def start_new_session(self, user_id: str, session_id: str):
        """
        Start a new conversation session

        In agent-stack, this means switching to a new thread_id.
        Each session is isolated - the agent won't have memory from previous sessions.

        Args:
            user_id: User identifier (creates isolated container)
            session_id: Session identifier (creates unique thread_id)
        """
        self.current_user_id = user_id
        self.current_session_id = session_id

        print(f"    [Starting new session: user={user_id}, session={session_id}]")
        print(f"    [Note: Agent is stateless - no memory from previous sessions]")

    def query(self, user_request: str, conversation_history: List[Dict]) -> Dict:
        """
        Query the agent with a user request

        Args:
            user_request: The user's query/request
            conversation_history: Previous turns in this session (currently NOT used by agent)

        Returns:
            {
                'response': str,  # Agent's response
                'tool_calls': [   # List of tools the agent called
                    {'tool': 'calculator', 'arguments': {...}, 'result': ...},
                    {'tool': 'search_web_with_content', 'arguments': {...}, 'result': ...}
                ]
            }
        """
        if not self.current_user_id or not self.current_session_id:
            raise ValueError("Must call start_new_session() before query()")

        try:
            # Call the agent endpoint
            url = f"{self.base_url}/u/{self.current_user_id}/chat"
            params = {
                'user_id': self.current_user_id,
                'session_id': self.current_session_id
            }
            data = {'message': user_request}

            response = self.session.post(
                url,
                params=params,
                json=data,
                timeout=120  # Agent may take time for tool calls
            )

            response.raise_for_status()
            result = response.json()

            # Parse the response
            agent_response = self._extract_response(result)
            tool_calls = self._extract_tool_calls(result)

            return {
                'response': agent_response,
                'tool_calls': tool_calls
            }

        except requests.exceptions.Timeout:
            print(f"    [Timeout waiting for agent response]")
            return {
                'response': '[Error: Request timeout - agent took too long to respond]',
                'tool_calls': []
            }
        except requests.exceptions.RequestException as e:
            print(f"    [Request error]: {str(e)}")
            return {
                'response': f'[Error: {str(e)}]',
                'tool_calls': []
            }
        except Exception as e:
            print(f"    [Unexpected error]: {str(e)}")
            return {
                'response': f'[Error: {str(e)}]',
                'tool_calls': []
            }

    def _extract_response(self, result: Dict) -> str:
        """
        Extract the agent's final response from the API result

        The agent returns a complex structure from LangGraph.
        We need to extract the final message content.

        Args:
            result: Raw API response

        Returns:
            The agent's response text
        """
        try:
            # LangGraph returns: {"result": {"messages": [...]}}
            if 'result' in result:
                result_data = result['result']

                # Get the last message (agent's final response)
                if 'messages' in result_data and result_data['messages']:
                    messages = result_data['messages']

                    # Find the last AI message
                    for msg in reversed(messages):
                        if isinstance(msg, dict):
                            # Handle different message formats
                            if msg.get('type') == 'ai' or 'content' in msg:
                                content = msg.get('content', '')
                                if content:
                                    return content
                            # Handle AIMessage objects
                            elif hasattr(msg, 'content'):
                                return msg.content

                    # Fallback: return the last message as string
                    last_msg = messages[-1]
                    if isinstance(last_msg, str):
                        return last_msg
                    elif isinstance(last_msg, dict):
                        return str(last_msg.get('content', last_msg))
                    else:
                        return str(last_msg)

            # Fallback: return the whole result as string
            return json.dumps(result, indent=2)

        except Exception as e:
            print(f"    [Warning: Error extracting response]: {e}")
            return str(result)

    def _extract_tool_calls(self, result: Dict) -> List[Dict]:
        """
        Extract tool calls from the API result

        The agent's tool usage is embedded in the message history.

        Args:
            result: Raw API response

        Returns:
            List of tool calls with format:
            [{'tool': str, 'arguments': dict, 'result': any, 'timestamp': str}, ...]
        """
        tool_calls = []

        try:
            if 'result' in result and 'messages' in result['result']:
                messages = result['result']['messages']

                for msg in messages:
                    if isinstance(msg, dict):
                        # Check for tool calls in AIMessage
                        if msg.get('type') == 'ai' and 'tool_calls' in msg:
                            for tool_call in msg['tool_calls']:
                                tool_calls.append({
                                    'tool': tool_call.get('name', 'unknown'),
                                    'arguments': tool_call.get('args', {}),
                                    'result': None,  # Result comes in next message
                                    'timestamp': datetime.now().isoformat()
                                })

                        # Check for tool results in ToolMessage
                        elif msg.get('type') == 'tool' and 'content' in msg:
                            # Match with previous tool call
                            if tool_calls and tool_calls[-1]['result'] is None:
                                tool_calls[-1]['result'] = msg['content']

        except Exception as e:
            print(f"    [Warning: Error extracting tool calls]: {e}")

        return tool_calls

    def health_check(self) -> bool:
        """
        Check if the agent is healthy and responsive

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/healthz", timeout=5)
            response.raise_for_status()
            data = response.json()
            return data.get('ok', False)
        except:
            return False


# For backward compatibility with baseline_evaluator.py
class AgentInterface(AgentStackInterface):
    """Alias for AgentStackInterface"""
    pass


if __name__ == "__main__":
    # Test the interface
    print("=" * 80)
    print("Testing AgentStackInterface")
    print("=" * 80)

    agent = AgentStackInterface()

    # Test health check
    print("\n1. Health Check:")
    if agent.health_check():
        print("  ✓ Agent is healthy")
    else:
        print("  ✗ Agent is not responding")
        exit(1)

    # Test a simple query
    print("\n2. Test Query:")
    agent.start_new_session("test_user", "test_session_1")

    response = agent.query(
        "Calculate 2 + 2 * 3",
        conversation_history=[]
    )

    print(f"  User: Calculate 2 + 2 * 3")
    print(f"  Agent: {response['response'][:200]}...")
    print(f"  Tool calls: {len(response['tool_calls'])}")

    for i, tool_call in enumerate(response['tool_calls'], 1):
        print(f"    {i}. {tool_call['tool']}({tool_call['arguments']})")

    print("\n" + "=" * 80)
    print("✓ Interface test complete")
    print("=" * 80)
