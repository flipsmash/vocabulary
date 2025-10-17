"""Infer and persist part-of-speech tags using heuristics and a local classifier."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

try:
    import mysql.connector
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "mysql-connector-python is required. Install it in your virtualenv via "
        "`pip install mysql-connector-python`."
    ) from exc

import numpy as np
from mysql.connector import MySQLConnection
from mysql.connector.cursor import MySQLCursorDict

try:
    from scipy.sparse import hstack
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "SciPy is required. Install it in your virtualenv via `pip install scipy`."
    ) from exc

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "scikit-learn is required. Install it in your virtualenv via "
        "`pip install scikit-learn`."
    ) from exc


VALID_POS = {"NOUN", "VERB", "ADJECTIVE", "ADVERB", "INTERJECTION", "PREPOSITION"}

PREFIX_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("to ", "VERB", "def_prefix:to"),
    ("a ", "NOUN", "def_prefix:a"),
    ("an ", "NOUN", "def_prefix:an"),
    ("the ", "NOUN", "def_prefix:the"),
    ("fear of ", "NOUN", "def_prefix:fear_of"),
    ("worship of ", "NOUN", "def_prefix:worship_of"),
    ("hatred of ", "NOUN", "def_prefix:hatred_of"),
    ("study of ", "NOUN", "def_prefix:study_of"),
    ("science of ", "NOUN", "def_prefix:science_of"),
    ("any of ", "NOUN", "def_prefix:any_of"),
    ("one who ", "NOUN", "def_prefix:one_who"),
    ("one that ", "NOUN", "def_prefix:one_that"),
    ("the act of ", "NOUN", "def_prefix:the_act_of"),
    ("the process of ", "NOUN", "def_prefix:the_process_of"),
    ("the state of ", "NOUN", "def_prefix:the_state_of"),
    ("the quality of ", "NOUN", "def_prefix:the_quality_of"),
    ("having ", "ADJECTIVE", "def_prefix:having"),
    ("of or relating to ", "ADJECTIVE", "def_prefix:of_or_relating_to"),
    ("characterized by ", "ADJECTIVE", "def_prefix:characterized_by"),
    ("tending to ", "ADJECTIVE", "def_prefix:tending_to"),
    ("pertaining to ", "ADJECTIVE", "def_prefix:pertaining_to"),
    ("full of ", "ADJECTIVE", "def_prefix:full_of"),
)

SUBSTRING_RULES: Tuple[Tuple[str, str, str], ...] = (
    (" fear of ", "NOUN", "def_contains:fear_of"),
    (" worship of ", "NOUN", "def_contains:worship_of"),
    (" hatred of ", "NOUN", "def_contains:hatred_of"),
)

SUFFIX_RULES: Tuple[Tuple[str, str, str], ...] = (
    ("ism", "NOUN", "suffix:ism"),
    ("ness", "NOUN", "suffix:ness"),
    ("tion", "NOUN", "suffix:tion"),
    ("ment", "NOUN", "suffix:ment"),
    ("ity", "NOUN", "suffix:ity"),
    ("ence", "NOUN", "suffix:ence"),
    ("ance", "NOUN", "suffix:ance"),
    ("logy", "NOUN", "suffix:logy"),
    ("graphy", "NOUN", "suffix:graphy"),
    ("graph", "NOUN", "suffix:graph"),
    ("gram", "NOUN", "suffix:gram"),
    ("meter", "NOUN", "suffix:meter"),
    ("scope", "NOUN", "suffix:scope"),
    ("phobia", "NOUN", "suffix:phobia"),
    ("phile", "NOUN", "suffix:phile"),
    ("cracy", "NOUN", "suffix:cracy"),
    ("crat", "NOUN", "suffix:crat"),
    ("ous", "ADJECTIVE", "suffix:ous"),
    ("less", "ADJECTIVE", "suffix:less"),
    ("ful", "ADJECTIVE", "suffix:ful"),
    ("able", "ADJECTIVE", "suffix:able"),
    ("ible", "ADJECTIVE", "suffix:ible"),
    ("ary", "ADJECTIVE", "suffix:ary"),
    ("ory", "ADJECTIVE", "suffix:ory"),
    ("al", "ADJECTIVE", "suffix:al"),
    ("ic", "ADJECTIVE", "suffix:ic"),
    ("ical", "ADJECTIVE", "suffix:ical"),
    ("ive", "ADJECTIVE", "suffix:ive"),
    ("oid", "ADJECTIVE", "suffix:oid"),
)

MIN_SUFFIX_LENGTH = 3


@dataclass(slots=True)
class DefinitionRecord:
    id: int
    term: str
    definition: str


@dataclass(slots=True)
class TrainingExample:
    term: str
    definition: str
    label: str


def normalize_term(term: str | None) -> str:
    return (term or "").strip().lower()


def normalize_definition_text(definition: str | None) -> str:
    text = (definition or "").strip()
    while text.startswith("("):
        close_idx = text.find(")")
        if close_idx == -1:
            break
        text = text[close_idx + 1 :].lstrip()
    return text.lower()


def configure_logging(log_file: str) -> None:
    log_format = "%(asctime)s %(levelname)s %(message)s"
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, mode="a", encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - filesystem issues are rare here
        logging.basicConfig(level=logging.INFO, format=log_format)
        logging.warning("Failed to attach file logger: %s", exc)
        return
    logging.basicConfig(level=logging.INFO, format=log_format, handlers=handlers)


def get_database_connection(args: argparse.Namespace) -> MySQLConnection:
    password = (
        args.password
        or os.getenv("VOCAB_DB_PASSWORD")
        or os.getenv("DB_PASSWORD")
    )
    if not password:
        raise SystemExit(
            "Database password not provided. Use --password or set VOCAB_DB_PASSWORD."
        )

    return mysql.connector.connect(
        host=args.db_host,
        user=args.db_user,
        password=password,
        database=args.db_name,
        autocommit=False,
    )


def fetch_training_examples(
    connection: MySQLConnection,
    limit: int | None,
) -> List[TrainingExample]:
    query = (
        "SELECT term, definition, part_of_speech FROM vocab.defined "
        "WHERE definition IS NOT NULL "
        "AND TRIM(definition) <> '' "
        "AND part_of_speech IS NOT NULL "
        "AND TRIM(part_of_speech) <> '' "
        "AND UPPER(part_of_speech) IN (%s)"
    )
    placeholders = ",".join(["%s"] * len(VALID_POS))
    query = query % placeholders

    params: List[str | int] = [label for label in sorted(VALID_POS)]
    if limit is not None:
        query += " LIMIT %s"
        params.append(limit)

    examples: List[TrainingExample] = []
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query, params)
        for row in cursor:
            term_norm = normalize_term(row["term"])
            definition_norm = normalize_definition_text(row["definition"])
            if not definition_norm:
                continue
            label = row["part_of_speech"].strip().upper()
            if label not in VALID_POS:
                continue
            examples.append(TrainingExample(term_norm, definition_norm, label))

    random.shuffle(examples)
    return examples


def prepare_training_examples(
    examples: List[TrainingExample],
    min_samples: int,
) -> Tuple[List[TrainingExample], Dict[str, int]]:
    counts = Counter(example.label for example in examples)
    eligible_labels = {label for label, count in counts.items() if count >= min_samples}
    if len(eligible_labels) < 2:
        raise SystemExit(
            "Not enough training data per label. Reduce --min-training-per-label or "
            "collect more labeled rows."
        )

    filtered = [ex for ex in examples if ex.label in eligible_labels]
    filtered_counts = Counter(ex.label for ex in filtered)
    return filtered, dict(filtered_counts)


class POSClassifier:
    def __init__(self, probability_threshold: float) -> None:
        self.probability_threshold = probability_threshold
        self.word_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=2)
        self.char_vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(3, 5), min_df=3)
        self.model = LogisticRegression(
            max_iter=2000,
            multi_class="multinomial",
            class_weight="balanced",
            C=2.0,
        )
        self._is_trained = False

    @staticmethod
    def build_features(term: str, definition: str) -> str:
        return f"{term} || {definition}"

    def fit(self, examples: Sequence[TrainingExample]) -> float:
        if not examples:
            raise SystemExit("No training examples available to fit the classifier.")

        texts = [self.build_features(ex.term, ex.definition) for ex in examples]
        labels = [ex.label for ex in examples]

        word_matrix = self.word_vectorizer.fit_transform(texts)
        char_matrix = self.char_vectorizer.fit_transform(texts)
        combined = hstack([word_matrix, char_matrix])
        self.model.fit(combined, labels)
        self._is_trained = True

        predictions = self.model.predict(combined)
        accuracy = float(np.mean(predictions == labels))
        return accuracy

    def predict(self, term: str, definition: str) -> Tuple[str, float]:
        if not self._is_trained:
            raise RuntimeError("Classifier has not been trained.")

        if not definition:
            return "", 0.0

        features = self.build_features(term, definition)
        word_matrix = self.word_vectorizer.transform([features])
        char_matrix = self.char_vectorizer.transform([features])
        combined = hstack([word_matrix, char_matrix])
        probabilities = self.model.predict_proba(combined)[0]
        best_index = int(np.argmax(probabilities))
        return self.model.classes_[best_index], float(probabilities[best_index])


def apply_heuristics(term: str, definition: str) -> Tuple[str | None, str | None]:
    if not definition:
        return None, None

    for prefix, label, rule_name in PREFIX_RULES:
        if definition.startswith(prefix):
            return label, rule_name

    for substring, label, rule_name in SUBSTRING_RULES:
        if substring in definition:
            return label, rule_name

    if definition.startswith("in a ") and (
        " manner" in definition or " way" in definition
    ):
        return "ADVERB", "def_prefix:in_a_manner"
    if definition.startswith("in an ") and (
        " manner" in definition or " way" in definition
    ):
        return "ADVERB", "def_prefix:in_an_manner"

    if term:
        for suffix, label, rule_name in SUFFIX_RULES:
            if len(term) > len(suffix) and term.endswith(suffix):
                return label, rule_name

    return None, None


def fetch_definition_batch(
    cursor: MySQLCursorDict,
    batch_size: int,
    last_id: int,
) -> List[DefinitionRecord]:
    query = (
        "SELECT id, term, definition FROM vocab.defined "
        "WHERE definition IS NOT NULL "
        "AND TRIM(definition) <> '' "
        "AND (part_of_speech IS NULL OR TRIM(part_of_speech) = '') "
        "AND id > %s ORDER BY id LIMIT %s"
    )
    cursor.execute(query, (last_id, batch_size))
    rows = cursor.fetchall()
    return [DefinitionRecord(**row) for row in rows]


def update_part_of_speech(
    connection: MySQLConnection,
    updates: Sequence[Tuple[str, int]],
) -> None:
    if not updates:
        return

    sql = "UPDATE vocab.defined SET part_of_speech = %s WHERE id = %s"
    with connection.cursor() as cursor:
        cursor.executemany(sql, updates)
    connection.commit()


def determine_pos(
    record: DefinitionRecord,
    classifier: POSClassifier,
) -> Tuple[str, str, str]:
    term_norm = normalize_term(record.term)
    definition_norm = normalize_definition_text(record.definition)

    heuristic_label, heuristic_rule = apply_heuristics(term_norm, definition_norm)
    if heuristic_label:
        return heuristic_label, heuristic_rule or "heuristic", "heuristic"

    predicted_label, probability = classifier.predict(term_norm, definition_norm)
    if predicted_label and probability >= classifier.probability_threshold:
        return (
            predicted_label,
            f"prob={probability:.3f}",
            "classifier",
        )

    return "TBD", f"prob={probability:.3f}", "classifier"


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Infer part-of-speech values for definitions lacking POS labels.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Number of rows to process per batch (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of rows to process before exiting.",
    )
    parser.add_argument(
        "--prob-threshold",
        type=float,
        default=0.8,
        help="Minimum classifier confidence required to accept a prediction.",
    )
    parser.add_argument(
        "--min-training-per-label",
        type=int,
        default=25,
        help="Minimum labeled rows required per POS label (default: %(default)s)",
    )
    parser.add_argument(
        "--training-limit",
        type=int,
        default=None,
        help="Optional limit on labeled rows pulled for training.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.0,
        help="Seconds to sleep between processed rows (default: %(default)s)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist updates. Without this flag the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--log-file",
        default="pos_inference.log",
        help="Path to an append-only log file (default: %(default)s)",
    )
    parser.add_argument("--db-host", default="10.0.0.160", help="Database host.")
    parser.add_argument("--db-name", default="vocab", help="Database name.")
    parser.add_argument("--db-user", default="brian", help="Database user.")
    parser.add_argument(
        "--password",
        help="Database password (overrides VOCAB_DB_PASSWORD if provided).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    configure_logging(args.log_file)

    logging.info(
        "Starting POS inference (dry-run=%s, batch_size=%s, prob_threshold=%.2f)",
        not args.commit,
        args.batch_size,
        args.prob_threshold,
    )

    connection = get_database_connection(args)

    try:
        training_examples = fetch_training_examples(connection, args.training_limit)
        filtered_examples, label_counts = prepare_training_examples(
            training_examples, args.min_training_per_label
        )
        classifier = POSClassifier(probability_threshold=args.prob_threshold)
        training_accuracy = classifier.fit(filtered_examples)
        logging.info(
            "Trained classifier on %s examples (labels=%s, training_accuracy=%.3f)",
            len(filtered_examples),
            label_counts,
            training_accuracy,
        )

        last_id = 0
        total_processed = 0
        total_updated = 0
        total_tbd = 0
        heuristic_updates = 0
        classifier_updates = 0

        with connection.cursor(dictionary=True) as cursor:
            while True:
                batch = fetch_definition_batch(cursor, args.batch_size, last_id)
                if not batch:
                    logging.info("No more candidate rows found. Exiting.")
                    break

                updates: List[Tuple[str, int]] = []

                for record in batch:
                    pos, detail, method = determine_pos(record, classifier)
                    total_processed += 1

                    logging.info(
                        "id=%s term=%s method=%s decision=%s detail=%s",
                        record.id,
                        record.term,
                        method,
                        pos,
                        detail,
                    )

                    if pos == "TBD":
                        total_tbd += 1
                    else:
                        updates.append((pos, record.id))
                        if method == "heuristic":
                            heuristic_updates += 1
                        else:
                            classifier_updates += 1

                    last_id = record.id

                    if args.limit and total_processed >= args.limit:
                        logging.info(
                            "Reached processing limit of %s rows.", args.limit
                        )
                        break

                    if args.sleep > 0:
                        time.sleep(args.sleep)

                if args.commit and updates:
                    update_part_of_speech(connection, updates)
                    total_updated += len(updates)
                    logging.info("Committed %s POS updates", len(updates))
                elif not args.commit and updates:
                    total_updated += len(updates)
                    logging.info(
                        "Dry-run: %s updates skipped (use --commit to persist)",
                        len(updates),
                    )

                if args.limit and total_processed >= args.limit:
                    break

        logging.info(
            "Finished. processed=%s updated=%s heuristic=%s classifier=%s "
            "skipped_tbd=%s dry_run=%s",
            total_processed,
            total_updated,
            heuristic_updates,
            classifier_updates,
            total_tbd,
            not args.commit,
        )
    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
