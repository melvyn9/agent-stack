"""
Baseline Evaluation Script for Agent Context/Memory Management

This script evaluates an agent WITHOUT context/memory management to establish baseline metrics.
It measures: task completion rate, tool call efficiency, response quality, and memory failures.

Usage:
    python baseline_evaluator.py --agent-endpoint <API_ENDPOINT> --output results.json
"""

import json
import argparse
from datetime import datetime
from typing import Dict, List, Any
import os


class BaselineEvaluator:
    """Evaluates agent baseline performance on context/memory management tasks"""

    def __init__(self, benchmark_file: str, agent_interface):
        """
        Initialize evaluator

        Args:
            benchmark_file: Path to test_requests_benchmark.json
            agent_interface: Interface to communicate with the agent (must implement query() method)
        """
        with open(benchmark_file, 'r', encoding='utf-8') as f:
            self.benchmark = json.load(f)

        self.agent = agent_interface
        self.results = {
            'evaluation_date': datetime.now().isoformat(),
            'benchmark_info': self.benchmark['benchmark_info'],
            'user_results': [],
            'overall_metrics': {}
        }

    def evaluate_all_users(self):
        """Run evaluation for all users in benchmark"""
        print("=" * 80)
        print("BASELINE EVALUATION - Agent WITHOUT Context/Memory Management")
        print("=" * 80)

        for user in self.benchmark['users']:
            print(f"\n[EVAL] Evaluating {user['user_id']}...")
            user_result = self.evaluate_user(user)
            self.results['user_results'].append(user_result)

        # Calculate overall metrics
        self.calculate_overall_metrics()

        print("\n" + "=" * 80)
        print("EVALUATION COMPLETE")
        print("=" * 80)

        return self.results

    def evaluate_user(self, user: Dict) -> Dict:
        """Evaluate all sessions for a single user"""
        user_result = {
            'user_id': user['user_id'],
            'profile': user['profile'],
            'sessions': [],
            'user_metrics': {}
        }

        all_responses = []
        all_tool_calls = []
        all_quality_scores = []
        memory_failures = []

        for session in user['sessions']:
            print(f"  Session {session['session_id']} ({session['session_info']['context_length']})")

            session_result = self.evaluate_session(user['user_id'], session)
            user_result['sessions'].append(session_result)

            # Aggregate data
            all_responses.extend(session_result['responses'])
            all_tool_calls.extend(session_result['tool_calls_log'])
            all_quality_scores.extend([r['quality_score'] for r in session_result['responses']])
            memory_failures.extend(session_result['memory_failures'])

        # Calculate user-level metrics
        user_result['user_metrics'] = {
            'total_requests': len(all_responses),
            'task_completion_rate': self.calculate_completion_rate(all_responses),
            'average_quality_score': sum(all_quality_scores) / len(all_quality_scores) if all_quality_scores else 0,
            'total_memory_failures': len(memory_failures),
            'total_tool_calls': len(all_tool_calls),
            'memory_failure_rate': len(memory_failures) / len(all_responses) if all_responses else 0
        }

        return user_result

    def evaluate_session(self, user_id: str, session: Dict) -> Dict:
        """
        Evaluate a single session

        NOTE: Each session should be run in a NEW conversation/context to simulate session boundaries
        """
        session_result = {
            'session_id': session['session_id'],
            'context_length': session['session_info']['context_length'],
            'tools_required': session['session_info']['tools_required'],
            'responses': [],
            'tool_calls_log': [],
            'memory_failures': [],
            'context_losses': []
        }

        # IMPORTANT: Start new session/conversation for this session
        # This simulates session boundaries where inter-session memory should be tested
        self.agent.start_new_session(user_id, session['session_id'])

        conversation_history = []

        for request in session['requests']:
            turn_num = request['turn']
            user_request = request['request']

            print(f"    Turn {turn_num}: {user_request[:60]}...")

            # Query agent
            response_data = self.agent.query(
                user_request=user_request,
                conversation_history=conversation_history
            )

            # Extract response and tool calls
            agent_response = response_data.get('response', '')
            tool_calls = response_data.get('tool_calls', [])

            # Update conversation history
            conversation_history.append({
                'turn': turn_num,
                'user': user_request,
                'agent': agent_response
            })

            # Evaluate this turn
            turn_eval = self.evaluate_turn(
                turn_num=turn_num,
                user_request=user_request,
                agent_response=agent_response,
                tool_calls=tool_calls,
                conversation_history=conversation_history,
                session_info=session
            )

            session_result['responses'].append(turn_eval)
            session_result['tool_calls_log'].extend(tool_calls)

            # Check for memory failures
            if turn_eval['memory_failure']:
                session_result['memory_failures'].append({
                    'turn': turn_num,
                    'request': user_request,
                    'failure_type': turn_eval['memory_failure_type'],
                    'description': turn_eval['memory_failure_description']
                })

            # Check for context loss
            if turn_eval['context_loss']:
                session_result['context_losses'].append({
                    'turn': turn_num,
                    'request': user_request,
                    'description': turn_eval['context_loss_description']
                })

        return session_result

    def evaluate_turn(self, turn_num: int, user_request: str, agent_response: str,
                     tool_calls: List[Dict], conversation_history: List[Dict],
                     session_info: Dict) -> Dict:
        """
        Evaluate a single turn

        This is where you manually assess response quality and detect failures.
        For automated evaluation, you could use LLM-as-judge or keyword matching.
        """
        turn_eval = {
            'turn': turn_num,
            'user_request': user_request,
            'agent_response': agent_response,
            'tool_calls': tool_calls,
            'task_completed': None,  # TODO: Mark True/False after manual review
            'quality_score': 0,  # TODO: Rate 1-5 after manual review
            'memory_failure': False,
            'memory_failure_type': None,
            'memory_failure_description': None,
            'context_loss': False,
            'context_loss_description': None,
            'redundant_tool_calls': self.detect_redundant_tools(tool_calls, conversation_history),
            'tool_violation': False,
            'tool_violation_description': None,
            'notes': ""
        }

        # Automated detection of obvious issues
        turn_eval.update(self.auto_detect_issues(
            user_request, agent_response, turn_num, session_info
        ))

        # Flag tool usage when tools should not be used
        allowed_tools = session_info.get('session_info', {}).get('tools_required', [])
        if isinstance(allowed_tools, list) and len(allowed_tools) == 0 and tool_calls:
            turn_eval['tool_violation'] = True
            turn_eval['tool_violation_description'] = "Tools were invoked in a no-tools session"

        return turn_eval

    def auto_detect_issues(self, user_request: str, agent_response: str,
                           turn_num: int, session_info: Dict) -> Dict:
        """
        Automatically detect common memory/context failures

        This is basic keyword-based detection. You should enhance this based on your agent.
        """
        issues = {
            'memory_failure': False,
            'memory_failure_type': None,
            'memory_failure_description': None
        }

        # Check if agent asks for already-provided information
        asking_keywords = [
            "what is your", "could you tell me", "can you remind me",
            "what was your", "do you remember", "what's your"
        ]

        reference_keywords = [
            "we calculated", "we discussed", "you mentioned",
            "last time", "before", "earlier", "previously"
        ]

        agent_lower = agent_response.lower()
        request_lower = user_request.lower()

        # User references past information
        if any(keyword in request_lower for keyword in reference_keywords):
            # Agent should recall this - check if it asks for clarification
            if any(keyword in agent_lower for keyword in asking_keywords):
                issues['memory_failure'] = True
                issues['memory_failure_type'] = 'inter_session_memory'
                issues['memory_failure_description'] = f"Agent asked for information that should be recalled from previous session/turn"

        return issues

    def detect_redundant_tools(self, current_tool_calls: List[Dict],
                               conversation_history: List[Dict]) -> List[Dict]:
        """
        Detect if agent is making redundant tool calls (re-searching same information)

        This indicates memory failure - agent should remember previous search results
        """
        redundant = []

        # Extract all previous tool calls from history
        # This is simplified - you'd need to track tool calls through conversation

        return redundant

    def calculate_completion_rate(self, responses: List[Dict]) -> float:
        """Calculate task completion rate from responses"""
        # Count responses marked as completed (requires manual review)
        completed = sum(1 for r in responses if r.get('task_completed') == True)
        total = len(responses)

        if total == 0:
            return 0.0

        # If not manually reviewed yet, return None to indicate pending
        if all(r.get('task_completed') is None for r in responses):
            return None

        return completed / total

    def calculate_overall_metrics(self):
        """Calculate overall metrics across all users"""
        all_quality_scores = []
        all_memory_failures = 0
        all_requests = 0
        all_tool_calls = 0

        for user_result in self.results['user_results']:
            user_metrics = user_result['user_metrics']
            all_requests += user_metrics['total_requests']
            all_memory_failures += user_metrics['total_memory_failures']
            all_tool_calls += user_metrics['total_tool_calls']

            # Collect quality scores
            for session in user_result['sessions']:
                for response in session['responses']:
                    if response['quality_score'] > 0:
                        all_quality_scores.append(response['quality_score'])

        self.results['overall_metrics'] = {
            'total_requests': all_requests,
            'total_memory_failures': all_memory_failures,
            'memory_failure_rate': all_memory_failures / all_requests if all_requests else 0,
            'average_quality_score': sum(all_quality_scores) / len(all_quality_scores) if all_quality_scores else None,
            'total_tool_calls': all_tool_calls,
            'average_tool_calls_per_request': all_tool_calls / all_requests if all_requests else 0
        }

    def save_results(self, output_file: str):
        """Save evaluation results to JSON file"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"\n[OK] Results saved to: {output_file}")

    def print_summary(self):
        """Print summary of evaluation results"""
        print("\n" + "=" * 80)
        print("EVALUATION SUMMARY")
        print("=" * 80)

        overall = self.results['overall_metrics']

        print(f"\n[METRICS] Overall Metrics:")
        print(f"  Total Requests: {overall['total_requests']}")
        print(f"  Total Memory Failures: {overall['total_memory_failures']}")
        print(f"  Memory Failure Rate: {overall['memory_failure_rate']:.2%}")
        print(f"  Average Quality Score: {overall.get('average_quality_score', 'Not rated')}")
        print(f"  Total Tool Calls: {overall['total_tool_calls']}")
        print(f"  Avg Tool Calls/Request: {overall['average_tool_calls_per_request']:.2f}")

        print(f"\n[USERS] Per-User Results:")
        for user_result in self.results['user_results']:
            user_id = user_result['user_id']
            metrics = user_result['user_metrics']
            print(f"\n  {user_id}:")
            print(f"    Total Requests: {metrics['total_requests']}")
            print(f"    Memory Failures: {metrics['total_memory_failures']}")
            print(f"    Memory Failure Rate: {metrics['memory_failure_rate']:.2%}")
            print(f"    Avg Quality Score: {metrics.get('average_quality_score', 'Not rated'):.2f}")


# ============================================================================
# Agent Interface - YOU NEED TO IMPLEMENT THIS FOR YOUR SPECIFIC AGENT
# ============================================================================

class AgentInterface:
    """
    Interface to communicate with your agent.

    YOU MUST IMPLEMENT THIS CLASS to connect to your specific agent deployment.
    """

    def __init__(self, endpoint: str = None, api_key: str = None):
        """
        Initialize connection to your agent

        Args:
            endpoint: API endpoint of your deployed agent
            api_key: API key if required
        """
        self.endpoint = endpoint
        self.api_key = api_key
        self.current_session_id = None

        # TODO: Initialize your agent client/connection here
        # Example: self.client = YourAgentClient(endpoint, api_key)

    def start_new_session(self, user_id: str, session_id: str):
        """
        Start a new conversation session

        This is CRITICAL - each session should be isolated to test inter-session memory
        """
        self.current_session_id = session_id

        # TODO: Initialize new session/conversation in your agent
        # This should clear any conversation context from previous sessions
        # Example: self.client.start_new_conversation(user_id, session_id)

        print(f"    [Starting new session: {session_id}]")

    def query(self, user_request: str, conversation_history: List[Dict]) -> Dict:
        """
        Query the agent with a user request

        Args:
            user_request: The user's query/request
            conversation_history: Previous turns in this session (for intra-session context)

        Returns:
            {
                'response': str,  # Agent's response
                'tool_calls': [   # List of tools the agent called
                    {'tool': 'web_search', 'query': '...', 'result': '...'},
                    {'tool': 'calculator', 'expression': '...', 'result': ...}
                ]
            }
        """
        # TODO: IMPLEMENT THIS - Send request to your agent and get response

        # Example implementation (replace with your actual agent API):
        # response_data = self.client.send_message(
        #     message=user_request,
        #     session_id=self.current_session_id,
        #     history=conversation_history
        # )

        # For now, return placeholder
        return {
            'response': f"[PLACEHOLDER - Implement AgentInterface.query() to connect to your agent]\nReceived: {user_request}",
            'tool_calls': []
        }


# ============================================================================
# Main Execution
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Evaluate baseline agent performance')
    parser.add_argument('--benchmark', default='test_requests_benchmark.json',
                       help='Path to benchmark JSON file')
    parser.add_argument('--agent-endpoint',
                       help='Agent API endpoint (if applicable)')
    parser.add_argument('--api-key',
                       help='API key for agent (if required)')
    parser.add_argument('--output', default='baseline_results.json',
                       help='Output file for results')

    args = parser.parse_args()

    # Initialize agent interface
    # YOU MUST CUSTOMIZE AgentInterface class above for your specific agent
    agent = AgentInterface(endpoint=args.agent_endpoint, api_key=args.api_key)

    # Initialize evaluator
    evaluator = BaselineEvaluator(
        benchmark_file=args.benchmark,
        agent_interface=agent
    )

    # Run evaluation
    results = evaluator.evaluate_all_users()

    # Save results
    evaluator.save_results(args.output)

    # Print summary
    evaluator.print_summary()

    print("\n" + "=" * 80)
    print("[NEXT] NEXT STEPS:")
    print("=" * 80)
    print("1. Implement AgentInterface class to connect to your deployed agent")
    print("2. Run the evaluation: python baseline_evaluator.py --agent-endpoint <URL>")
    print("3. Manually review results and rate quality_score (1-5) and task_completed (True/False)")
    print("4. Re-calculate metrics after manual review")
    print("5. Document qualitative examples of baseline weaknesses for your report")
    print("=" * 80)


if __name__ == '__main__':
    main()
