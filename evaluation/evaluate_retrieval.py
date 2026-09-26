import json
import sys
from pathlib import Path

from dotenv import load_dotenv


# Add backend directory to Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))


# Load configuration before embedding.py initializes its OpenAI client.
load_dotenv(BACKEND_DIR / ".env")

from app.embedding import create_embeddings
from app.repository import search_chunks


QUESTIONS_FILE = Path(__file__).parent / "questions.json"


def load_questions():
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def is_hit(retrieved_pages, ground_truth_pages, k):
    top_k_pages = retrieved_pages[:k]

    return any(
        page in ground_truth_pages
        for page in top_k_pages
    )


def evaluate():
    questions = load_questions()

    hit_at_1 = 0
    hit_at_3 = 0
    hit_at_5 = 0

    results = []

    print("\n========================================")
    print("RAG Retrieval Evaluation")
    print("========================================\n")

    for item in questions:
        question = item["question"]
        paper_id = item["paper_id"]
        ground_truth_pages = item["ground_truth_pages"]

        # Create embedding for the question
        query_embedding = create_embeddings([question])[0]

        # Retrieve Top-5 chunks
        retrieved_chunks = search_chunks(
            paper_id=paper_id,
            query_embedding=query_embedding,
            limit=5,
        )

        retrieved_pages = [
            chunk["page_number"]
            for chunk in retrieved_chunks
        ]

        h1 = is_hit(
            retrieved_pages,
            ground_truth_pages,
            1,
        )

        h3 = is_hit(
            retrieved_pages,
            ground_truth_pages,
            3,
        )

        h5 = is_hit(
            retrieved_pages,
            ground_truth_pages,
            5,
        )

        hit_at_1 += int(h1)
        hit_at_3 += int(h3)
        hit_at_5 += int(h5)

        results.append(
            {
                "id": item["id"],
                "question": question,
                "ground_truth_pages": ground_truth_pages,
                "retrieved_pages": retrieved_pages,
                "hit@1": h1,
                "hit@3": h3,
                "hit@5": h5,
            }
        )

        print(item["id"])
        print(f"Question: {question}")
        print(f"Ground truth: {ground_truth_pages}")
        print(f"Retrieved:    {retrieved_pages}")
        print(
            f"Hit@1: {'PASS' if h1 else 'FAIL'} | "
            f"Hit@3: {'PASS' if h3 else 'FAIL'} | "
            f"Hit@5: {'PASS' if h5 else 'FAIL'}"
        )
        print("-" * 40)

    total = len(questions)

    hit_1_rate = hit_at_1 / total
    hit_3_rate = hit_at_3 / total
    hit_5_rate = hit_at_5 / total

    print("\n========================================")
    print("Summary")
    print("========================================")

    print(f"Questions: {total}")
    print(f"Hit@1: {hit_at_1}/{total} ({hit_1_rate:.1%})")
    print(f"Hit@3: {hit_at_3}/{total} ({hit_3_rate:.1%})")
    print(f"Hit@5: {hit_at_5}/{total} ({hit_5_rate:.1%})")

    # Save detailed results
    output = {
        "total_questions": total,
        "hit_at_1": hit_1_rate,
        "hit_at_3": hit_3_rate,
        "hit_at_5": hit_5_rate,
        "results": results,
    }

    results_file = Path(__file__).parent / "results.json"

    with open(
        results_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\nDetailed results saved to: {results_file}")


if __name__ == "__main__":
    evaluate()