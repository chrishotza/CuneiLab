"""Explain Unicode OCR errors by tablet, sign and edit operation.

Diagnostic alignment uses exact Unicode sign codepoints, not model tokenizer IDs.
No images or model weights are downloaded.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from transcription import glyph_tokens, TranscriptionError
from scripts.evaluate_nabu import read_jsonl, evaluate

MAX_ALIGN_TOKENS = 1500


def tokens(text: str, *, cropped_faces: bool = False) -> list[str]:
    sequence = glyph_tokens(text)
    return [s for s in sequence if not s.startswith('@')] if cropped_faces else sequence


def align(reference: list[str], predicted: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Optimal global alignment; deterministic diagonal > deletion > insertion ties.

    O(n*m) memory; capped to avoid unbounded memory from malformed inputs.
    """
    n, m = len(reference), len(predicted)
    if max(n, m) > MAX_ALIGN_TOKENS:
        raise ValueError(f'La alineación detallada admite máximo {MAX_ALIGN_TOKENS} tokens por lectura')
    matrix = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        matrix[i][0] = i
    for j in range(m + 1):
        matrix[0][j] = j
    for i, expected in enumerate(reference, 1):
        current, previous = matrix[i], matrix[i - 1]
        for j, observed in enumerate(predicted, 1):
            current[j] = min(previous[j - 1] + (expected != observed),
                             previous[j] + 1, current[j - 1] + 1)
    i, j = n, m
    edits = []
    while i or j:
        if i and j and matrix[i][j] == matrix[i-1][j-1] + (reference[i-1] != predicted[j-1]):
            edits.append(('correct' if reference[i-1] == predicted[j-1] else 'substitution',
                          reference[i-1], predicted[j-1]))
            i -= 1
            j -= 1
        elif i and matrix[i][j] == matrix[i-1][j] + 1:
            edits.append(('deletion', reference[i-1], None))
            i -= 1
        else:
            edits.append(('insertion', None, predicted[j-1]))
            j -= 1
    return list(reversed(edits))


def _leaderboard(counter: Counter, limit: int) -> list[dict]:
    return [{'token': key, 'count': count}
            for key, count in sorted(counter.items(), key=lambda x: (-x[1], x[0]))[:limit]]


def analyze(gold: dict[str, str], predicted: dict[str, str],
            *, cropped_faces: bool = False, top: int = 25) -> dict:
    if type(top) is not int or not 1 <= top <= 100:
        raise ValueError('top debe estar entre 1 y 100')
    # Existing scoring remains the canonical metric. Never silently replace it.
    baseline = evaluate(gold, predicted, cropped_faces=cropped_faces)
    substitutions: Counter = Counter()
    deletions: Counter = Counter()
    insertions: Counter = Counter()
    pairs: Counter = Counter()
    by_tablet = []
    totals: Counter = Counter()

    for identifier in sorted(gold):
        reference = tokens(gold[identifier], cropped_faces=cropped_faces)
        prediction = tokens(predicted.get(identifier, ''), cropped_faces=cropped_faces)
        if not reference:
            raise ValueError(f'{identifier}: referencia sin signos válidos')
        edits = align(reference, prediction)
        counts = Counter(operation for operation, _, _ in edits)
        totals.update(counts)
        for operation, expected, observed in edits:
            if operation == 'substitution':
                substitutions[expected] += 1
                pairs[(expected, observed)] += 1
            elif operation == 'deletion':
                deletions[expected] += 1
            elif operation == 'insertion':
                insertions[observed] += 1
        edit_count = sum(counts[op] for op in ('substitution','deletion','insertion'))
        by_tablet.append({
            'id': identifier,
            'status': 'missing_prediction' if identifier not in predicted else 'scored',
            'reference_tokens': len(reference),
            'predicted_tokens': len(prediction),
            'edit_errors': edit_count,
            'sign_error_rate': edit_count / len(reference),
            'substitutions': counts['substitution'],
            'deletions': counts['deletion'],
            'insertions': counts['insertion'],
        })
    by_tablet.sort(key=lambda row: (-row['sign_error_rate'], -row['edit_errors'], row['id']))
    # A check against canonical edit-distance makes implementation drift obvious.
    expected_errors = baseline['total_edit_errors'] + baseline['missing_reference_signs']
    actual_errors = sum(totals[op] for op in ('substitution', 'deletion', 'insertion'))
    if expected_errors != actual_errors:
        raise AssertionError('Alineación y evaluación principal difieren: resultado no publicable')
    return {
        'format': 'cuneilab-ocr-error-analysis',
        'version': 1,
        'cropped_faces': cropped_faces,
        'evaluation': {key: baseline[key] for key in (
            'images_scored', 'coverage_images', 'micro_sign_error_rate',
            'micro_sign_error_rate_including_missing', 'missing_predictions',
            'unmatched_predictions', 'reference_signs', 'all_reference_signs'
        )},
        'totals': {key: totals[key] for key in ('correct','substitution','deletion','insertion')},
        'most_substituted_reference_signs': _leaderboard(substitutions, top),
        'most_deleted_reference_signs': _leaderboard(deletions, top),
        'most_inserted_predicted_signs': _leaderboard(insertions, top),
        'most_common_substitutions': [
            {'reference': a, 'prediction': b, 'count': count}
            for (a, b), count in sorted(pairs.items(), key=lambda entry:
                (-entry[1], entry[0][0], entry[0][1]))[:top]
        ],
        'worst_tablets': by_tablet[:top],
        'limitations': ('Unicode edit alignment is deterministic but ambiguous for repeated signs; '
                        'confusions are diagnostics, not calibrated model probabilities. '
                        'Missing predictions count as deletions. '
                        'The benchmark does not establish independence from model training.'),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analizar confusiones OCR por signo y por tablilla')
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--predicted', type=Path, required=True)
    parser.add_argument('--cropped-faces', action='store_true')
    parser.add_argument('--top', type=int, default=25)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze(read_jsonl(args.gold), read_jsonl(args.predicted),
                         cropped_faces=args.cropped_faces, top=args.top)
    except (ValueError, TranscriptionError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f'Error: {error}\n')
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + '\n', encoding='utf-8')
    print(rendered)


if __name__ == '__main__':
    main()
