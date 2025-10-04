#!/usr/bin/env python3
"""Domain classifier CLI for assigning vocabulary terms to taxonomy domains.

This module implements a hybrid rule-based and semantic similarity classifier that
assigns a primary domain to a term/definition pair drawn from the project's
standard taxonomy. It exposes a reusable :class:`DomainClassifier` for library
use and a rich command-line interface for batch processing from CSV or
PostgreSQL sources.

Key features
------------
* Deterministic hybrid scoring (rules + embeddings) with tunable fusion.
* YAML-driven configuration with a generated default profile.
* Sentence-transformer embeddings with automatic TF-IDF fallback.
* Detailed evidence tracing for auditing and optional JSONL dumps.
* Production-oriented CLI supporting CSV + PostgreSQL I/O.
* Self-test harness to validate out-of-the-box behaviour.

The module is intentionally self-contained (single file) yet extensively
documented for maintainability.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import regex
import yaml
from pydantic import BaseModel, Field, ValidationError

try:  # Optional dependencies imported lazily later when required.
    import torch
except Exception:  # pragma: no cover - torch is optional
    torch = None

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:  # pragma: no cover - psycopg2 optional when PG not used
    psycopg2 = None
    execute_values = None


LOGGER = logging.getLogger("domain_classifier")
IDENTIFIER_PATTERN = regex.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

REQUIREMENTS_TXT = """\
domain-classifier
------------------
pandas>=2.0
pyyaml>=6.0
regex>=2023.0
pydantic>=1.10
sentence-transformers>=2.2
scikit-learn>=1.3
psycopg2-binary>=2.9
"""

DEFAULT_CONFIG_NAME = "domains.default.yaml"
DEFAULT_RANDOM_SEED = 42

TAXONOMY = [
    "General / Cross-Domain",
    "Language & Literature",
    "Arts & Culture",
    "Life Sciences",
    "Medicine & Health Sciences",
    "Physical Sciences & Engineering",
    "Chemistry & Materials",
    "Mathematics & Logic",
    "Technology & Computing",
    "Business, Economics & Finance",
    "Law, Government & Civics",
    "Social & Behavioral Sciences",
    "Religion, Philosophy & Mythology",
    "Geography, Earth & Environment",
    "Maritime & Navigation",
    "Material Culture & Applied Skills",
    "Military & Security",
]

# NOTE: The default config is intentionally compact yet high-signal. Project
# teams are encouraged to augment the keywords/regexes via YAML.
DEFAULT_CONFIG_YAML = r"""
weights:
  alpha: 1.0
  beta: 1.0
thresholds:
  low: 0.45
  tie_delta: 0.03
embedding_model: "all-MiniLM-L6-v2"
preprocessing:
  lemmatize: false
  strip_stopwords: false
domains:
  - name: "General / Cross-Domain"
    description: "Fallback domain for terms without clear specialised signal."
    seed_examples:
      - generalist
      - commonplace
      - everyday word
    keywords: []
    negative_keywords: []
    regexes: []
    base_weight: 0.1
  - name: "Language & Literature"
    description: "Linguistics, literary devices, grammar, etymology, and philology."
    seed_examples:
      - phoneme
      - alliteration
      - grammar
      - lexicon
      - syntax
      - morphology
      - allegory
      - rhetoric
      - etymology
      - sonnet
    keywords:
      - phoneme
      - morpheme
      - allophone
      - anaphora
      - zeugma
      - etymology
      - prosody
      - lexicon
      - syntax
      - clause
    negative_keywords:
      - algorithm
    regexes:
      - pattern: "\\b(stanza|sonnet|meter|metre|verse)\\b"
        weight: 0.35
        description: "Poetic structure terms"
    base_weight: 0.45
  - name: "Arts & Culture"
    description: "Visual and performing arts, cultural studies, and aesthetics."
    seed_examples:
      - chiaroscuro
      - sonata
      - iconography
      - ballet
      - folklore
      - motif
      - fresco
      - dramaturgy
      - opera
      - sculpture
    keywords:
      - choreography
      - sonata
      - fresco
      - canvas
      - iconography
      - motif
      - curator
      - gallery
      - dramaturgy
    negative_keywords:
      - statute
      - theorem
    regexes:
      - pattern: "\\b(chiaroscuro|polyphony|trompe-l'oeil)\\b"
        weight: 0.4
        description: "Specialised art terminology"
    base_weight: 0.45
  - name: "Life Sciences"
    description: "Biology, ecology, botany, zoology, and organismal sciences."
    seed_examples:
      - photosynthesis
      - enzyme
      - species
      - genus
      - mitosis
      - chloroplast
      - ecosystem
      - biosphere
      - allele
      - taxonomy
    keywords:
      - enzyme
      - species
      - organism
      - habitat
      - cellular
      - photosynthesis
      - respiration
      - genome
      - taxonomy
      - biodiversity
    negative_keywords:
      - algorithm
      - statute
    regexes:
      - pattern: "\\b[A-Z][a-z]+\\s[a-z]+\\b"
        weight: 0.45
        description: "Latin binomial nomenclature"
    base_weight: 0.5
  - name: "Medicine & Health Sciences"
    description: "Clinical practice, anatomy, pathology, and medical terminology."
    seed_examples:
      - pathology
      - symptom
      - diagnosis
      - hemodynamics
      - pharmacology
      - neurology
      - analgesic
      - hematology
      - epidemiology
      - physiology
    keywords:
      - symptom
      - diagnosis
      - pathology
      - clinical
      - patient
      - therapeutic
      - syndrome
      - anatomy
      - pharmacology
    negative_keywords:
      - species
    regexes:
      - pattern: "\\b(itis|osis|algia|ectomy|emia|opathy|phagia|plasty)\\b"
        weight: 0.5
        description: "Medical suffix detection"
    base_weight: 0.55
  - name: "Physical Sciences & Engineering"
    description: "Physics, mechanical and electrical engineering, and related sciences."
    seed_examples:
      - torque
      - momentum
      - dielectric
      - inertia
      - capacitor
      - gearbox
      - thermodynamics
      - oscillator
      - resonance
      - wavelength
    keywords:
      - torque
      - momentum
      - velocity
      - gear
      - circuit
      - dielectric
      - resonance
      - vector
      - actuator
      - inertia
    negative_keywords:
      - statute
      - mythology
    regexes:
      - pattern: "\\b(Newton|Pascal|joule|ampere|volt|ohm)s?\\b"
        weight: 0.4
        description: "SI unit references"
    base_weight: 0.5
  - name: "Chemistry & Materials"
    description: "Chemical compounds, reactions, materials science, and mineralogy."
    seed_examples:
      - polymer
      - catalysis
      - oxidation
      - ligand
      - isomer
      - crystalline lattice
      - alloy
      - reagent
      - stoichiometry
      - electrolyte
    keywords:
      - catalyst
      - reagent
      - polymer
      - crystalline
      - alloy
      - solvent
      - molarity
      - stoichiometry
      - precipitate
    negative_keywords:
      - statute
      - theorem
    regexes:
      - pattern: "\\b([A-Z][a-z]?\\d+){1,}\\b"
        weight: 0.6
        description: "Chemical formula"
      - pattern: "\\b(ate|ite|ole|ol|one|ine|ium)s?\\b"
        weight: 0.35
        description: "Chemical suffix"
    base_weight: 0.55
  - name: "Mathematics & Logic"
    description: "Mathematical structures, proofs, logic, and quantitative reasoning."
    seed_examples:
      - theorem
      - lemma
      - bijection
      - manifold
      - integral
      - calculus
      - predicate logic
      - boolean algebra
      - topology
      - isomorphism
    keywords:
      - lemma
      - theorem
      - axiom
      - proof
      - manifold
      - bijection
      - boolean
      - predicate
      - quantifier
      - vector space
    negative_keywords:
      - statute
      - mythology
    regexes:
      - pattern: "\\b(group|ring|field|algebra)s?\\b"
        weight: 0.45
        description: "Abstract algebra term"
    base_weight: 0.55
  - name: "Technology & Computing"
    description: "Computer science, software, hardware, and information systems."
    seed_examples:
      - algorithm
      - hash
      - kernel
      - protocol
      - compiler
      - database
      - encryption
      - bytecode
      - microprocessor
      - virtualization
    keywords:
      - algorithm
      - hash
      - protocol
      - compiler
      - database
      - encryption
      - kernel
      - byte
      - firmware
      - cloud
    negative_keywords:
      - species
      - statute
    regexes:
      - pattern: "\\b(api|sdk|cli|bios)\\b"
        weight: 0.4
        description: "Acronyms common in computing"
    base_weight: 0.5
  - name: "Business, Economics & Finance"
    description: "Commerce, markets, accounting, management, and financial instruments."
    seed_examples:
      - dividend
      - leverage
      - arbitrage
      - ledger
      - derivative
      - profit margin
      - balance sheet
      - capital expenditure
      - bond yield
      - risk premium
    keywords:
      - dividend
      - leverage
      - arbitrage
      - ledger
      - bond
      - derivative
      - portfolio
      - equity
      - marginal
      - revenue
    negative_keywords:
      - theorem
      - enzyme
    regexes:
      - pattern: "\\b(P&L|ROI|EBITDA)\\b"
        weight: 0.45
        description: "Finance acronyms"
    base_weight: 0.5
  - name: "Law, Government & Civics"
    description: "Legal systems, governance, policy, and civic processes."
    seed_examples:
      - statute
      - ordinance
      - jurisdiction
      - plaintiff
      - tort
      - precedent
      - legislature
      - habeas corpus
      - constitution
      - administrative law
    keywords:
      - statute
      - tort
      - jurisdiction
      - ordinance
      - plaintiff
      - defendant
      - precedent
      - legislature
      - court
      - constitution
    negative_keywords:
      - theorem
      - enzyme
    regexes:
      - pattern: "\\b(v\\.\\s|vs\\.|et\\sal\\.|habeas|amicus)\\b"
        weight: 0.4
        description: "Legal Latin / abbreviations"
    base_weight: 0.55
  - name: "Social & Behavioral Sciences"
    description: "Psychology, sociology, anthropology, and human behaviour."
    seed_examples:
      - cognition
      - ethnography
      - sociology
      - anthropology
      - survey methodology
      - social norm
      - behaviourism
      - psyche
      - demography
      - qualitative research
    keywords:
      - cognition
      - norm
      - ethnography
      - sociology
      - anthropology
      - survey
      - behaviour
      - culture
      - demography
      - psychosocial
    negative_keywords:
      - algorithm
      - torque
    regexes:
      - pattern: "\\b(psych(o|-)\\w+)"
        weight: 0.4
        description: "Psychology terms"
    base_weight: 0.45
  - name: "Religion, Philosophy & Mythology"
    description: "Religious studies, philosophy, theology, and mythic traditions."
    seed_examples:
      - ontology
      - epistemology
      - pantheon
      - soteriology
      - teleology
      - metaphysics
      - liturgy
      - exegesis
      - monotheism
      - mythic narrative
    keywords:
      - ontology
      - epistemology
      - pantheon
      - theology
      - liturgy
      - doctrine
      - metaphysics
      - deity
      - ritual
      - mythology
    negative_keywords:
      - algorithm
    regexes:
      - pattern: "\\b(soteriology|teleology|eschatology)\\b"
        weight: 0.45
        description: "Philosophical/theological terms"
    base_weight: 0.5
  - name: "Geography, Earth & Environment"
    description: "Geosciences, climatology, environmental science, and geography."
    seed_examples:
      - watershed
      - tectonic
      - sedimentary
      - biome
      - erosion
      - lithosphere
      - climatology
      - permafrost
      - estuary
      - geomorphology
    keywords:
      - sedimentary
      - tectonic
      - watershed
      - biome
      - erosion
      - estuary
      - lithosphere
      - climate
      - geomorphology
      - ecology
    negative_keywords:
      - statute
      - algorithm
    regexes:
      - pattern: "\\b(latitude|longitude|isobar|isotherm)\\b"
        weight: 0.35
        description: "Geospatial terminology"
    base_weight: 0.45
  - name: "Maritime & Navigation"
    description: "Seafaring, naval operations, navigation tools, and maritime practices."
    seed_examples:
      - keel
      - aft
      - starboard
      - sextant
      - astrolabe
      - dead reckoning
      - bilge
      - brigantine
      - sonar
      - convoy
    keywords:
      - keel
      - starboard
      - portside
      - aft
      - sextant
      - astrolabe
      - bilge
      - convoy
      - helm
      - ballast
    negative_keywords:
      - statute
      - theorem
    regexes:
      - pattern: "\\b(naval|abaft|bo'sun|boatswain)\\b"
        weight: 0.4
        description: "Nautical jargon"
    base_weight: 0.5
  - name: "Material Culture & Applied Skills"
    description: "Craftsmanship, tools, culinary arts, agriculture, and practical trades."
    seed_examples:
      - loom
      - fermentation
      - kiln
      - solder
      - tincture
      - horticulture
      - textile
      - carpentry
      - metallurgy
      - pottery
    keywords:
      - loom
      - fermentation
      - kiln
      - solder
      - tincture
      - horticulture
      - textile
      - craftsmanship
      - forge
      - artisan
    negative_keywords:
      - statute
      - theorem
    regexes:
      - pattern: "\\b(handcraft|apprentice|smithing)\\b"
        weight: 0.35
        description: "Craft terminology"
    base_weight: 0.45
  - name: "Military & Security"
    description: "Armed forces, strategy, intelligence, and security operations."
    seed_examples:
      - sortie
      - bivouac
      - flank
      - ballistics
      - counterintelligence
      - reconnaissance
      - battalion
      - ordinance
      - SIGINT
      - garrison
    keywords:
      - sortie
      - bivouac
      - flank
      - artillery
      - reconnaissance
      - intelligence
      - SIGINT
      - counterintelligence
      - garrison
      - brigade
    negative_keywords:
      - theorem
      - enzyme
    regexes:
      - pattern: "\\b(ops?|counter-?intel|special forces)\\b"
        weight: 0.4
        description: "Military abbreviations"
    base_weight: 0.5
"""


# ---------------------------------------------------------------------------
# Utility data models and helper structures
# ---------------------------------------------------------------------------


class RegexRuleConfig(BaseModel):
    """Configuration for a regex-based rule."""

    pattern: str
    weight: float = 0.3
    description: str = ""


class DomainConfig(BaseModel):
    """Configuration block for a single taxonomy domain."""

    name: str
    description: str
    seed_examples: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    negative_keywords: List[str] = Field(default_factory=list)
    regexes: List[RegexRuleConfig] = Field(default_factory=list)
    base_weight: float = 0.4


class WeightsConfig(BaseModel):
    alpha: float = 1.0
    beta: float = 1.0


class ThresholdsConfig(BaseModel):
    low: float = 0.45
    tie_delta: float = 0.03


class PreprocessingConfig(BaseModel):
    lemmatize: bool = False
    strip_stopwords: bool = False


class ClassifierConfig(BaseModel):
    domains: List[DomainConfig]
    weights: WeightsConfig = WeightsConfig()
    thresholds: ThresholdsConfig = ThresholdsConfig()
    embedding_model: str = "all-MiniLM-L6-v2"
    preprocessing: PreprocessingConfig = PreprocessingConfig()


@dataclass
class DomainResources:
    """Runtime resources for a domain after config compilation."""

    config: DomainConfig
    keyword_patterns: List[regex.Pattern] = field(default_factory=list)
    negative_patterns: List[regex.Pattern] = field(default_factory=list)
    regex_rules: List[Tuple[regex.Pattern, float, str, str]] = field(
        default_factory=list
    )  # compiled pattern, weight, description, raw pattern


# ---------------------------------------------------------------------------
# Deterministic seeds
# ---------------------------------------------------------------------------


def _initialise_random_seeds(seed: int = DEFAULT_RANDOM_SEED) -> None:
    """Set seeds for random number generators to ensure determinism."""

    random.seed(seed)
    np.random.seed(seed)
    if torch is not None:  # pragma: no cover - torch optional
        try:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Text preprocessing helpers
# ---------------------------------------------------------------------------


try:  # Optional resource for lemmatization / stopwords
    from sklearn.feature_extraction import text as sk_text
except ImportError:  # pragma: no cover - handled gracefully later
    sk_text = None


def _build_stopword_set() -> Optional[set[str]]:
    if sk_text is None:
        return None
    return set(sk_text.ENGLISH_STOP_WORDS)


try:  # pragma: no cover - optional
    from nltk.stem import WordNetLemmatizer
except ImportError:  # pragma: no cover - optional dependency
    WordNetLemmatizer = None


# ---------------------------------------------------------------------------
# Embedding backends
# ---------------------------------------------------------------------------


class EmbeddingBackend:
    """Abstract interface for embedding text snippets."""

    def encode(self, texts: Sequence[str]) -> np.ndarray:  # pragma: no cover - ABC
        raise NotImplementedError


class SentenceTransformerBackend(EmbeddingBackend):
    """Sentence-Transformer powered embeddings."""

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        embeddings = self.model.encode(
            list(texts),
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=False,
        )
        return embeddings.astype(np.float32)


class TfidfBackend(EmbeddingBackend):
    """Fallback embedding using TF-IDF cosine space."""

    def __init__(self, prototype_texts: Sequence[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer()
        self.prototype_matrix = self.vectorizer.fit_transform(prototype_texts)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return self.vectorizer.transform(texts).astype(np.float32)


# ---------------------------------------------------------------------------
# Domain classifier implementation
# ---------------------------------------------------------------------------


class DomainClassifier:
    """Hybrid rule + semantic classifier for taxonomy domains."""

    def __init__(
        self,
        config_path: Optional[str] = None,
        *,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        threshold_low: Optional[float] = None,
        tie_delta: Optional[float] = None,
        config_output_dir: Optional[str] = None,
    ) -> None:
        _initialise_random_seeds()

        self.base_dir = Path(config_output_dir or Path(__file__).resolve().parent)
        self.default_config_path = self.base_dir / DEFAULT_CONFIG_NAME

        if config_path:
            config_file = Path(config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
        else:
            config_file = self.default_config_path
            if not config_file.exists():
                LOGGER.info(
                    "No config supplied; writing default config to %s",
                    config_file,
                )
                config_file.parent.mkdir(parents=True, exist_ok=True)
                config_file.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")

        self.config_path = config_file
        with config_file.open("r", encoding="utf-8") as handle:
            raw_cfg = yaml.safe_load(handle)

        try:
            self.config = ClassifierConfig.parse_obj(raw_cfg)
        except ValidationError as exc:  # pragma: no cover - configuration errors
            raise ValueError(f"Invalid configuration: {exc}") from exc

        # Apply CLI overrides if provided.
        if alpha is not None:
            self.config.weights.alpha = float(alpha)
        if beta is not None:
            self.config.weights.beta = float(beta)
        if threshold_low is not None:
            self.config.thresholds.low = float(threshold_low)
        if tie_delta is not None:
            self.config.thresholds.tie_delta = float(tie_delta)

        self.domain_order = [domain.name for domain in self.config.domains]
        missing = [name for name in TAXONOMY if name not in self.domain_order]
        if missing:
            raise ValueError(
                "Configuration missing taxonomy domains: " f"{', '.join(missing)}"
            )

        # Compile domain resources for rule evaluation.
        self.domain_resources: Dict[str, DomainResources] = {}
        for domain in self.config.domains:
            keyword_patterns = [
                regex.compile(rf"\b{regex.escape(word.lower())}\b", regex.IGNORECASE)
                for word in domain.keywords
            ]
            negative_patterns = [
                regex.compile(rf"\b{regex.escape(word.lower())}\b", regex.IGNORECASE)
                for word in domain.negative_keywords
            ]
            regex_rules = [
                (
                    regex.compile(rule.pattern, regex.IGNORECASE),
                    float(rule.weight),
                    rule.description,
                    rule.pattern,
                )
                for rule in domain.regexes
            ]
            self.domain_resources[domain.name] = DomainResources(
                config=domain,
                keyword_patterns=keyword_patterns,
                negative_patterns=negative_patterns,
                regex_rules=regex_rules,
            )

        # Pre-calc prototypes for semantic scoring.
        self.prototype_texts = [self._prototype_text(domain) for domain in self.config.domains]
        self.embedding_backend: EmbeddingBackend
        self.prototype_embeddings: Optional[np.ndarray] = None
        self._semantic_backend_label = "tfidf"

        try:
            self.embedding_backend = SentenceTransformerBackend(
                self.config.embedding_model
            )
            self._semantic_backend_label = "sentence-transformers"
            LOGGER.info(
                "Loaded sentence-transformer model '%s'", self.config.embedding_model
            )
        except Exception as exc:  # pragma: no cover - fallback path
            LOGGER.warning(
                "Falling back to TF-IDF embeddings because sentence-transformer \n"
                "model '%s' could not be initialised (%s)",
                self.config.embedding_model,
                exc,
            )
            self.embedding_backend = TfidfBackend(self.prototype_texts)
            self.prototype_embeddings = self.embedding_backend.encode(
                self.prototype_texts
            ).toarray()  # type: ignore[attr-defined]

        if self.prototype_embeddings is None:
            self.prototype_embeddings = self.embedding_backend.encode(
                self.prototype_texts
            )

        self.prototype_embeddings = self._l2_normalise(self.prototype_embeddings)

        self.stopwords = _build_stopword_set()
        if not self.config.preprocessing.strip_stopwords:
            self.stopwords = None

        self.lemmatizer = None
        if self.config.preprocessing.lemmatize:
            if WordNetLemmatizer is None:  # pragma: no cover - optional path
                LOGGER.warning("Lemmatization requested but NLTK WordNet is unavailable")
            else:
                self.lemmatizer = WordNetLemmatizer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_one(self, term: str, definition: str) -> Dict[str, Any]:
        """Classify a single term/definition pair.

        Parameters
        ----------
        term:
            The vocabulary term/headword.
        definition:
            Corresponding definition text.

        Returns
        -------
        dict
            Structured classification output including scores and evidence.
        """

        results = self.classify_batch([term], [definition])
        return results[0]

    def classify_batch(
        self, terms: Sequence[str], definitions: Sequence[str]
    ) -> List[Dict[str, Any]]:
        """Classify multiple term/definition pairs.

        Notes
        -----
        * Rule-scoring is executed per record.
        * Embeddings are computed in batch for efficiency.
        """

        if len(terms) != len(definitions):
            raise ValueError("Terms and definitions must have matching lengths")

        clean_terms = [term or "" for term in terms]
        clean_defs = [definition or "" for definition in definitions]

        preprocessed_defs = [self._preprocess_text(text) for text in clean_defs]
        rule_scores_list: List[Dict[str, float]] = []
        rule_evidence_list: List[Dict[str, Dict[str, Any]]] = []

        for processed_text in preprocessed_defs:
            scores, evidence = self._score_rules(processed_text)
            rule_scores_list.append(scores)
            rule_evidence_list.append(evidence)

        semantic_matrix = self._compute_semantic_scores(clean_defs)

        outputs: List[Dict[str, Any]] = []
        alpha = self.config.weights.alpha
        beta = self.config.weights.beta
        threshold_low = self.config.thresholds.low
        tie_delta = self.config.thresholds.tie_delta

        for idx, term in enumerate(clean_terms):
            definition = clean_defs[idx]
            rule_scores = rule_scores_list[idx]
            sem_vector = semantic_matrix[idx]

            sem_min = float(np.min(sem_vector))
            sem_max = float(np.max(sem_vector))
            if math.isclose(sem_min, sem_max):
                norm_sem = np.array([0.5] * len(self.domain_order), dtype=np.float32)
            else:
                norm_sem = (sem_vector - sem_min) / (sem_max - sem_min)

            fused_scores: Dict[str, float] = {}
            for domain_idx, domain_name in enumerate(self.domain_order):
                rule_score = rule_scores.get(domain_name, 0.0)
                sem_score = float(norm_sem[domain_idx])
                fused = alpha * rule_score + beta * sem_score
                fused_scores[domain_name] = fused

            sorted_domains = sorted(
                fused_scores.items(), key=lambda item: item[1], reverse=True
            )
            primary_domain, best_score = sorted_domains[0]
            alt_score = sorted_domains[1][1] if len(sorted_domains) > 1 else 0.0
            borderline = (best_score - alt_score) <= tie_delta

            if best_score < threshold_low:
                primary_domain = "General / Cross-Domain"

            semantic_top = sorted(
                (
                    {
                        "domain": domain,
                        "cosine": float(value),
                    }
                    for domain, value in zip(self.domain_order, sem_vector)
                ),
                key=lambda item: item["cosine"],
                reverse=True,
            )[:3]

            evidence_payload = {
                "matched_keywords": {
                    domain: data["keywords"]
                    for domain, data in rule_evidence_list[idx].items()
                    if data["keywords"]
                },
                "negative_keywords": {
                    domain: data["negative_keywords"]
                    for domain, data in rule_evidence_list[idx].items()
                    if data["negative_keywords"]
                },
                "matched_regexes": {
                    domain: data["regexes"]
                    for domain, data in rule_evidence_list[idx].items()
                    if data["regexes"]
                },
                "top_semantic_domains": semantic_top,
                "borderline": borderline,
                "semantic_backend": self._semantic_backend_label,
            }

            outputs.append(
                {
                    "term": term,
                    "definition": definition,
                    "primary_domain": primary_domain,
                    "confidence": float(best_score),
                    "scores": fused_scores,
                    "evidence": evidence_payload,
                }
            )

        return outputs

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prototype_text(self, domain: DomainConfig) -> str:
        examples = ", ".join(domain.seed_examples[:40])
        fragments = [
            domain.name,
            domain.description,
            f"Seed examples: {examples}" if examples else "",
        ]
        return ". ".join(fragment for fragment in fragments if fragment)

    @staticmethod
    def _l2_normalise(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def _preprocess_text(self, text: str) -> str:
        lower = text.lower()
        cleaned = regex.sub(r"[^\p{L}\p{N}\s\-]", " ", lower)
        cleaned = regex.sub(r"\s+", " ", cleaned).strip()
        if self.stopwords:
            tokens = [
                token
                for token in cleaned.split()
                if token not in self.stopwords
            ]
            cleaned = " ".join(tokens)
        if self.lemmatizer:
            tokens = [self.lemmatizer.lemmatize(token) for token in cleaned.split()]
            cleaned = " ".join(tokens)
        return cleaned

    def _score_rules(self, processed_text: str) -> Tuple[Dict[str, float], Dict[str, Dict[str, Any]]]:
        scores: Dict[str, float] = {}
        evidence: Dict[str, Dict[str, Any]] = {}

        for domain_name in self.domain_order:
            resources = self.domain_resources[domain_name]
            base_weight = max(resources.config.base_weight, 0.0)
            matched_keywords = []
            matched_negative = []
            matched_regexes = []
            raw_score = 0.0

            for pattern, keyword in zip(
                resources.keyword_patterns, resources.config.keywords
            ):
                if pattern.search(processed_text):
                    matched_keywords.append(keyword)
                    raw_score += base_weight

            for pattern, keyword in zip(
                resources.negative_patterns, resources.config.negative_keywords
            ):
                if pattern.search(processed_text):
                    matched_negative.append(keyword)

            for compiled, weight, description, raw_pattern in resources.regex_rules:
                if compiled.search(processed_text):
                    matched_regexes.append(
                        {
                            "pattern": raw_pattern,
                            "weight": weight,
                            "description": description,
                        }
                    )
                    raw_score += weight

            if matched_negative:
                raw_score = max(0.0, raw_score - (base_weight / 2.0) * len(matched_negative))

            rule_score = 1.0 - math.exp(-raw_score)
            scores[domain_name] = float(rule_score)
            evidence[domain_name] = {
                "keywords": matched_keywords,
                "negative_keywords": matched_negative,
                "regexes": matched_regexes,
                "raw_rule_score": raw_score,
                "rule_score": rule_score,
            }

        return scores, evidence

    def _compute_semantic_scores(self, definitions: Sequence[str]) -> np.ndarray:
        embeddings = self.embedding_backend.encode(definitions)
        if hasattr(embeddings, "toarray"):
            embeddings = embeddings.toarray()
        embeddings = embeddings.astype(np.float32)
        embeddings = self._l2_normalise(embeddings)
        sims = embeddings @ self.prototype_embeddings.T
        return sims


# ---------------------------------------------------------------------------
# CLI utilities
# ---------------------------------------------------------------------------


def parse_pg_resource(resource: str) -> Tuple[str, str, str]:
    """Parse a PostgreSQL resource string with optional schema/table suffix."""

    if "#" in resource:
        base, suffix = resource.split("#", 1)
        suffix = suffix.strip()
        if not suffix:
            raise ValueError("PostgreSQL resource must include table name after '#'")
        if "." in suffix:
            schema, table = suffix.split(".", 1)
        else:
            schema, table = "public", suffix
    else:
        base = resource
        schema, table = "public", ""

    for identifier in filter(None, [schema, table]):
        if not IDENTIFIER_PATTERN.match(identifier):
            raise ValueError(f"Invalid PostgreSQL identifier: {identifier}")

    return base, schema, table


def _validate_column_name(name: str) -> str:
    if not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid column identifier: {name}")
    return name


def read_from_postgres(
    resource: str,
    term_col: str,
    def_col: str,
) -> Tuple[List[str], List[str]]:
    if psycopg2 is None:  # pragma: no cover - runtime guard
        raise ImportError("psycopg2-binary is required for PostgreSQL operations")

    conn_str, schema, table = parse_pg_resource(resource)
    if not table:
        raise ValueError("PostgreSQL read requires a table (use '#schema.table')")

    term_col = _validate_column_name(term_col)
    def_col = _validate_column_name(def_col)

    LOGGER.info("Reading terms from %s.%s", schema, table)
    terms: List[str] = []
    definitions: List[str] = []

    with psycopg2.connect(conn_str) as conn:
        with conn.cursor() as cur:
            query = (
                f"SELECT {term_col}, {def_col} FROM {schema}.{table} "
                f"WHERE {def_col} IS NOT NULL"
            )
            cur.execute(query)
            for record in cur.fetchall():
                terms.append(record[0])
                definitions.append(record[1])

    return terms, definitions


def ensure_output_table(
    resource: str,
    upsert_column: Optional[str],
) -> Tuple[psycopg2.extensions.connection, str, str]:
    if psycopg2 is None:  # pragma: no cover - runtime guard
        raise ImportError("psycopg2-binary is required for PostgreSQL operations")

    conn_str, schema, table = parse_pg_resource(resource)
    if not table:
        raise ValueError("PostgreSQL write requires a table (use '#schema.table')")

    conn = psycopg2.connect(conn_str)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {schema}.{table} ("
            "term TEXT PRIMARY KEY,"
            "definition TEXT,"
            "primary_domain TEXT,"
            "confidence DOUBLE PRECISION,"
            "scores_json JSONB,"
            "evidence_json JSONB,"
            "processed_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        )
        conn.commit()

    if upsert_column and upsert_column != "term":
        upsert_column = _validate_column_name(upsert_column)
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_{upsert_column} "
                f"ON {schema}.{table} ({upsert_column})"
            )
            conn.commit()

    return conn, schema, table


def write_to_postgres(
    resource: str,
    rows: Sequence[Dict[str, Any]],
    upsert_column: Optional[str] = None,
) -> None:
    if not rows:
        LOGGER.warning("No rows to write to PostgreSQL")
        return

    upsert_column_validated = None
    if upsert_column is not None:
        upsert_column_validated = _validate_column_name(upsert_column)

    conn, schema, table = ensure_output_table(resource, upsert_column_validated)
    column = upsert_column_validated or "term"
    if execute_values is None:  # pragma: no cover - safety guard
        raise ImportError("psycopg2-binary's execute_values is required")

    records = [
        (
            row["term"],
            row["definition"],
            row["primary_domain"],
            row["confidence"],
            json.dumps(row["scores"], ensure_ascii=False),
            json.dumps(row["evidence"], ensure_ascii=False),
        )
        for row in rows
    ]

    placeholders = "(term, definition, primary_domain, confidence, scores_json, evidence_json)"
    conflict_clause = (
        f"ON CONFLICT ({column}) DO UPDATE SET "
        "definition = EXCLUDED.definition, "
        "primary_domain = EXCLUDED.primary_domain, "
        "confidence = EXCLUDED.confidence, "
        "scores_json = EXCLUDED.scores_json, "
        "evidence_json = EXCLUDED.evidence_json, "
        "processed_at = NOW()"
        if upsert_column_validated is not None
        else ""
    )

    with conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                f"INSERT INTO {schema}.{table} {placeholders} VALUES %s {conflict_clause}",
                records,
            )
    conn.close()


def dump_jsonl(path: str, records: Iterable[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Self-test suite
# ---------------------------------------------------------------------------


SELF_TEST_CASES = [
    (
        "meningitis",
        "Inflammation of the protective membranes covering the brain and spinal cord.",
        "Medicine & Health Sciences",
    ),
    (
        "group isomorphism",
        "An isomorphism between algebraic groups preserving the group operation.",
        "Mathematics & Logic",
    ),
    (
        "statute",
        "A law enacted by a legislative body and codified for enforcement.",
        "Law, Government & Civics",
    ),
    (
        "kiln",
        "A furnace used for firing pottery, bricks, or drying grain in artisanal crafts.",
        "Material Culture & Applied Skills",
    ),
]


def run_self_test(classifier: DomainClassifier) -> None:
    from collections import Counter

    results = classifier.classify_batch(
        [term for term, _, _ in SELF_TEST_CASES],
        [definition for _, definition, _ in SELF_TEST_CASES],
    )

    headers = ["Term", "Expected", "Predicted", "Confidence"]
    table_rows = []
    success = True
    scores = []

    for row, (_, _, expected) in zip(results, SELF_TEST_CASES):
        predicted = row["primary_domain"]
        confidence = row["confidence"]
        scores.append(confidence)
        if predicted != expected or confidence < 0.6:
            success = False
        table_rows.append((row["term"], expected, predicted, f"{confidence:.2f}"))

    print("\nSELF-TEST RESULTS")
    print("=================")
    print(f"Backend: {classifier._semantic_backend_label}")
    print()
    widths = [max(len(str(val)) for val in col) for col in zip(headers, *table_rows)]
    header_line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("-+-".join("-" * w for w in widths))
    for row in table_rows:
        print(" | ".join(str(val).ljust(w) for val, w in zip(row, widths)))

    print()
    confidence_counter = Counter(
        ">=0.6" if score >= 0.6 else "<0.6" for score in scores
    )
    for bucket, count in confidence_counter.items():
        print(f"{count} predictions {bucket}")

    print()
    if success:
        print("Self-test PASSED: all sample classifications confident and correct.")
    else:
        print(
            "Self-test WARNING: at least one sample classification weak. "
            "Review configuration or thresholds."
        )


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument("--input-csv", help="Path to input CSV file")
    input_group.add_argument("--pg-read", help="PostgreSQL source URI")

    parser.add_argument("--term-col", default="term", help="Term column in CSV")
    parser.add_argument(
        "--def-col", default="definition", help="Definition column in CSV"
    )
    parser.add_argument("--pg-term-col", default=None, help="Term column for PG read")
    parser.add_argument("--pg-def-col", default=None, help="Definition column for PG read")

    parser.add_argument("--output-csv", help="Optional output CSV path")
    parser.add_argument("--pg-write", help="PostgreSQL destination URI")
    parser.add_argument(
        "--pg-upsert-on",
        help="Column name for UPSERT conflict resolution (defaults to term)",
    )

    parser.add_argument("--config", help="Path to YAML configuration file")
    parser.add_argument(
        "--config-output-dir",
        help="Directory for writing the default configuration when none exists",
    )

    parser.add_argument("--alpha", type=float, help="Override alpha weight")
    parser.add_argument("--beta", type=float, help="Override beta weight")
    parser.add_argument(
        "--threshold-low",
        type=float,
        dest="threshold_low",
        help="Override low-confidence threshold",
    )
    parser.add_argument(
        "--tie-delta",
        type=float,
        help="Override borderline delta between top domains",
    )
    parser.add_argument(
        "--topk",
        type=int,
        default=0,
        help="Include top-k domains as additional columns in CSV output",
    )
    parser.add_argument(
        "--dump-explanations",
        help="Write per-record evidence to JSONL at the specified path",
    )
    parser.add_argument(
        "--print-requirements",
        action="store_true",
        help="Print pip requirements and exit",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in smoke tests and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Set logging verbosity",
    )

    return parser.parse_args(argv)


def load_input_data(args: argparse.Namespace) -> Tuple[List[str], List[str]]:
    if args.input_csv:
        LOGGER.info("Reading input CSV from %s", args.input_csv)
        df = pd.read_csv(args.input_csv)
        if args.term_col not in df.columns or args.def_col not in df.columns:
            raise ValueError("CSV lacks the specified term/definition columns")
        terms = df[args.term_col].astype(str).tolist()
        definitions = df[args.def_col].astype(str).tolist()
        return terms, definitions

    if args.pg_read:
        term_col = args.pg_term_col or args.term_col
        def_col = args.pg_def_col or args.def_col
        return read_from_postgres(args.pg_read, term_col, def_col)

    raise ValueError("Either --input-csv or --pg-read must be provided")


def attach_topk_columns(
    records: List[Dict[str, Any]],
    topk: int,
) -> pd.DataFrame:
    df = pd.DataFrame(records)
    if topk <= 0:
        df["scores_json"] = df["scores"].apply(lambda obj: json.dumps(obj, ensure_ascii=False))
        df["evidence_json"] = df["evidence"].apply(
            lambda obj: json.dumps(obj, ensure_ascii=False)
        )
        return df.drop(columns=["scores", "evidence"], errors="ignore")

    def topk_extractor(score_map: Mapping[str, float]) -> List[Tuple[str, float]]:
        return sorted(score_map.items(), key=lambda item: item[1], reverse=True)[:topk]

    topk_columns: Dict[str, List[Any]] = {}
    for row in records:
        top_items = topk_extractor(row["scores"])
        for idx, (domain, score) in enumerate(top_items, start=1):
            topk_columns.setdefault(f"top{idx}_domain", []).append(domain)
            topk_columns.setdefault(f"top{idx}_score", []).append(score)
        for idx in range(len(top_items) + 1, topk + 1):
            topk_columns.setdefault(f"top{idx}_domain", []).append("")
            topk_columns.setdefault(f"top{idx}_score", []).append(np.nan)

    df = pd.DataFrame(records)
    for column, values in topk_columns.items():
        df[column] = values

    df["scores_json"] = df["scores"].apply(lambda obj: json.dumps(obj, ensure_ascii=False))
    df["evidence_json"] = df["evidence"].apply(
        lambda obj: json.dumps(obj, ensure_ascii=False)
    )

    return df.drop(columns=["scores", "evidence"], errors="ignore")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.print_requirements:
        print(REQUIREMENTS_TXT)
        return 0

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    classifier = DomainClassifier(
        config_path=args.config,
        alpha=args.alpha,
        beta=args.beta,
        threshold_low=args.threshold_low,
        tie_delta=args.tie_delta,
        config_output_dir=args.config_output_dir,
    )

    if args.self_test:
        run_self_test(classifier)
        return 0

    terms, definitions = load_input_data(args)
    records = classifier.classify_batch(terms, definitions)

    if args.dump_explanations:
        LOGGER.info("Writing explanations to %s", args.dump_explanations)
        dump_jsonl(args.dump_explanations, records)

    if args.output_csv:
        LOGGER.info("Writing CSV predictions to %s", args.output_csv)
        df = attach_topk_columns(records, args.topk)
        df.to_csv(args.output_csv, index=False)

    if args.pg_write:
        LOGGER.info("Writing predictions to PostgreSQL destination")
        write_to_postgres(args.pg_write, records, args.pg_upsert_on)

    if not args.output_csv and not args.pg_write and not args.dump_explanations:
        writer = csv.writer(sys.stdout)
        writer.writerow(["term", "primary_domain", "confidence"])
        for row in records:
            writer.writerow([row["term"], row["primary_domain"], f"{row['confidence']:.4f}"])

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
