"""Collect answers from the shared Ask Paper pipeline for manual review."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_FILE = Path(__file__).resolve().parent / 'questions.json'
OUTPUT_FILE = Path(__file__).resolve().parent / 'generation_results.json'
METRICS = ('answer_correctness', 'groundedness', 'citation_correctness')
CITATION_PATTERN = re.compile(r'\[(Pages?\s+[^\]]+)\]', flags=re.IGNORECASE)
PAGE_LIST_PATTERN = re.compile(
    r'Pages?\s+\d+(?:(?:\s*[,;]\s*|\s+and\s+)(?:Pages?\s+)?\d+)*',
    flags=re.IGNORECASE,
)


def extract_citations(answer):
    """Extract ordered, unique page numbers from supported citation lists.

    Supported examples include ``[Page 3]``, ``[Page 3; Page 4]`` and
    ``[Pages 2, 7, 8]``. Ambiguous forms such as page ranges remain in the
    unparsed list so a reviewer can inspect them instead of silently guessing.
    """
    citations = [match.group(0) for match in CITATION_PATTERN.finditer(answer)]
    pages = []
    unparsed = []
    for citation in citations:
        body = citation[1:-1]
        if PAGE_LIST_PATTERN.fullmatch(body):
            citation_pages = [int(value) for value in re.findall(r'\d+', body)]
            for page in citation_pages:
                if page not in pages:
                    pages.append(page)
        else:
            unparsed.append(citation)
    return pages, unparsed


def reparse_saved_citations(data):
    """Refresh derived citation fields without changing benchmark answers."""
    updated = 0
    for row in data.get('results', []):
        if row.get('status') != 'completed' or not isinstance(row.get('answer'), str):
            continue
        cited_pages, unparsed = extract_citations(row['answer'])
        if row.get('cited_pages') != cited_pages or row.get('unparsed_citations') != unparsed:
            row['cited_pages'] = cited_pages
            row['unparsed_citations'] = unparsed
            updated += 1
    return updated


def collect_answer(item, ask):
    response = ask(item['paper_id'], item['question'], include_context=True)
    cited_pages, unparsed = extract_citations(response['answer'])
    return {
        **item,
        'status': 'completed',
        'answer': response['answer'],
        'retrieved_pages': [source['page_number'] for source in response['sources']],
        'cited_pages': cited_pages,
        'unparsed_citations': unparsed,
        'sources': response['sources'],
        'retrieved_chunks': response['retrieved_chunks'],
        'review': {**{metric: None for metric in METRICS}, 'notes': ''},
    }


def summarize(data):
    rows = data['results']
    print(f"Questions: {data['total_questions']}")
    print(f"Completed: {sum(row['status'] == 'completed' for row in rows)}")
    print(f"Errors: {sum(row['status'] == 'error' for row in rows)}")
    for metric in METRICS:
        grades = [row.get('review', {}).get(metric) for row in rows if row['status'] == 'completed']
        if any(grade is not None and type(grade) is not bool for grade in grades):
            raise ValueError(f'{metric}: use true, false, or null for manual grades')
        reviewed = sum(type(grade) is bool for grade in grades)
        passed = sum(grade is True for grade in grades)
        score = f'{passed} / {reviewed} ({passed / reviewed:.1%})' if reviewed else 'Not reviewed'
        print(f'{metric}: {score}; reviewed {reviewed}/{data["total_questions"]}')


def save(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def evaluate(questions_path, output_path, ask, resume=False):
    questions = json.loads(questions_path.read_text(encoding='utf-8'))
    if not isinstance(questions, list) or not questions:
        raise ValueError('Questions must be a nonempty JSON array')
    ids = [item['id'] for item in questions]
    if len(set(ids)) != len(ids):
        raise ValueError('Question IDs must be unique')
    data = {'total_questions': len(questions), 'started_at': datetime.now(timezone.utc).isoformat(), 'pipeline': 'app.ask_service.answer_question', 'results': []}
    if output_path.exists():
        if not resume:
            raise ValueError(f'{output_path} already exists. Use --resume or choose another --output.')
        data = json.loads(output_path.read_text(encoding='utf-8'))
        if data['total_questions'] != len(questions):
            raise ValueError('Dataset changed; choose a new --output file')
        expected = {item['id']: item for item in questions}
        for row in data['results']:
            if row['id'] not in expected or any(row.get(key) != value for key, value in expected[row['id']].items()):
                raise ValueError('Dataset changed; choose a new --output file')
    existing = {row['id']: row for row in data['results']}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(questions, 1):
        if existing.get(item['id'], {}).get('status') == 'completed':
            print(f'[{index}/{len(questions)}] {item["id"]}: kept saved answer', flush=True)
            continue
        print(f'[{index}/{len(questions)}] {item["id"]}: generating…', flush=True)
        try:
            row = collect_answer(item, ask)
        except Exception as error:
            row = {**item, 'status': 'error', 'error': f'{type(error).__name__}: {error}'}
            print(f'  Failed: {type(error).__name__}', flush=True)
        existing[item['id']] = row
        data['results'] = [existing[q['id']] for q in questions if q['id'] in existing]
        save(output_path, data)
    summarize(data)
    print(f'Saved: {output_path}')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--questions', type=Path, default=QUESTIONS_FILE)
    parser.add_argument('--output', type=Path, default=OUTPUT_FILE)
    parser.add_argument('--resume', action='store_true', help='Keep completed answers and manual grades; retry failed/missing questions')
    parser.add_argument('--summary', action='store_true', help='Summarize existing manual grades without API calls')
    parser.add_argument('--reparse-citations', action='store_true', help='Refresh cited_pages from saved answers without API calls')
    args = parser.parse_args()
    if args.reparse_citations:
        data = json.loads(args.output.read_text(encoding='utf-8'))
        updated = reparse_saved_citations(data)
        save(args.output, data)
        print(f'Reparsed citations in {updated} result(s). Saved: {args.output}')
        return
    if args.summary:
        summarize(json.loads(args.output.read_text(encoding='utf-8')))
        return
    sys.path.insert(0, str(PROJECT_ROOT / 'backend'))
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / 'backend' / '.env')
    from app.ask_service import answer_question
    data = evaluate(args.questions, args.output, answer_question, args.resume)
    if any(row['status'] == 'error' for row in data['results']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
