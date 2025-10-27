import argparse
import os
import sys
from baseline_evaluator import BaselineEvaluator
from agent_stack_interface import AgentStackInterface


def main():
    parser = argparse.ArgumentParser(
        description='Run agent-stack baseline evaluation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--benchmark',
        default='benchmark.json',
    )

    parser.add_argument(
        '--agent-url',
        default='http://52.27.245.205:7000',
    )

    parser.add_argument(
        '--output',
        default='baseline_results.json',
    )

    args = parser.parse_args()

    # Check if benchmark file exists
    if not os.path.exists(args.benchmark):
        print(f"[ERROR] Benchmark file not found: {args.benchmark}")
        sys.exit(1)

    print("=" * 80)
    print("BASELINE EVALUATION - agent-stack")
    print("=" * 80)
    print(f"Agent URL: {args.agent_url}")
    print(f"Benchmark: {args.benchmark}")
    print(f"Output: {args.output}")
    print("=" * 80)
    print()

    # Create agent interface
    try:
        agent = AgentStackInterface(base_url=args.agent_url)
        print("[OK] Agent interface initialized successfully\n")

        # Test health
        if not agent.health_check():
            print("[!] Warning: Agent health check failed")
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("Aborted.")
                sys.exit(1)

    except Exception as e:
        print(f"[ERROR] Failed to initialize agent: {str(e)}")
        sys.exit(1)

    # Create evaluator
    try:
        evaluator = BaselineEvaluator(
            benchmark_file=args.benchmark,
            agent_interface=agent
        )
        print("[OK] Evaluator initialized successfully\n")

    except Exception as e:
        print(f"[ERROR] Failed to initialize evaluator: {str(e)}")
        sys.exit(1)

    # Run evaluation
    print("\nRun evaluation...")

    try:
        results = evaluator.evaluate_all_users()

        # Save results
        evaluator.save_results(args.output)

        # Print summary
        evaluator.print_summary()

        print("[OK] Evaluation completed!")

    except KeyboardInterrupt:
        print("\n\n[!] Evaluation interrupted by user")
        sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] Exception during evaluation: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
