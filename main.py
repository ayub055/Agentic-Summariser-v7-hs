"""Main entry point for Transaction Intelligence System."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import MODEL_NAME
from data.loader import get_data_summary
from pipeline import TransactionPipeline
from utils.helpers import print_header


# =============================================================================
# PIPELINE DEMOS
# =============================================================================

def demo_pipeline_basic():
    """Demo the new structured pipeline with streaming."""
    print_header("Pipeline - Basic Query")
    pipeline = TransactionPipeline(verbose=True)

    queries = [
        "How much did customer 1 spend on Groceries?",
        "What is customer 2's total income?",
        "Show me top 3 spending categories for customer 1",
    ]

    for q in queries:
        print("\n[Answer (streaming)]")
        print("-" * 60)
        for chunk in pipeline.query_stream(q):
            print(chunk, end='', flush=True)
        print("\n" + "-" * 60)


def demo_pipeline_interactive():
    """Interactive pipeline mode with streaming."""
    print_header("Pipeline - Interactive Mode")
    print("Type questions about customer transactions.")
    print("Type 'quit' to exit.\n")

    pipeline = TransactionPipeline(verbose=True)

    while True:
        try:
            question = input("\nYou: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            if not question:
                continue

            print("\n[Answer]")
            print("-" * 60)
            for chunk in pipeline.query_stream(question):
                print(chunk, end='', flush=True)
            print("\n" + "-" * 60)

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break


def demo_pipeline_fast():
    """Pipeline without LLM explainer (faster)."""
    print_header("Pipeline - Fast Mode (No LLM Explainer)")
    pipeline = TransactionPipeline(use_llm_explainer=False, verbose=True)

    response = pipeline.query("What are the top 5 spending categories for customer 1?")
    print(f"\nFast response:\n{response.answer}")


def demo_pipeline_streaming():
    """Demo streaming output."""
    print_header("Pipeline - Streaming Demo")
    pipeline = TransactionPipeline(verbose=True)

    query = "Generate a full report for customer 9449274898"
    print(f"\nQuery: {query}\n")
    print("[Answer (streaming)]")
    print("-" * 60)

    for chunk in pipeline.query_stream(query):
        print(chunk, end='', flush=True)

    print("\n" + "-" * 60)


# =============================================================================
# MAIN
# =============================================================================

def main():
    print_header("Transaction Intelligence System", "=", 60)
    print(f"\nModels: mistral (parser), {MODEL_NAME} (explainer)")
    print("Make sure Ollama is running: 'ollama serve'\n")

    print("Loading transaction data...")
    print(get_data_summary())

    print("\n" + "="*60)
    print("SELECT MODE:")
    print("="*60)
    print("  1. Basic pipeline demo")
    print("  2. Interactive pipeline (with streaming)")
    print("  3. Fast mode (no LLM explainer)")
    print("  4. Streaming demo")
    print("\n  q. Quit")

    choice = input("\nChoice: ").strip()

    demos = {
        '1': demo_pipeline_basic,
        '2': demo_pipeline_interactive,
        '3': demo_pipeline_fast,
        '4': demo_pipeline_streaming,
    }

    if choice in demos:
        demos[choice]()
    elif choice.lower() == 'q':
        print("Goodbye!")
    else:
        print("Invalid choice. Running pipeline demo...")
        demo_pipeline_basic()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nError: {e}")
        print("\nMake sure:")
        print("1. Ollama is running ('ollama serve')")
        print("2. Models installed: 'ollama pull mistral' and 'ollama pull llama3.2'")
        print("3. Transaction data exists in data/rgs.csv")
