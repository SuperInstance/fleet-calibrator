"""
fleet_calibrator/probes.py — Standard probe suites for critical angle measurement.

Each probe is a (question, expected_answer) pair. Run against a model,
measure accuracy, detect phase transitions by varying difficulty.

These are the SAME probes that generated F1-F25. Standardized so
any model can be calibrated by any agent at any time.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ProbeSuite:
    """A set of probes for measuring critical angles in one domain."""
    domain: str
    probes: List[Tuple[str, str]]  # (question, expected_answer)
    difficulty_levels: List[str]   # ordered from easy to hard


# ─── Addition Depth Probes ────────────────────────────────────────────────────

def addition_depth_probes(max_depth: int = 25) -> ProbeSuite:
    """Generate addition chain probes of increasing depth.

    Depth 1: a + b
    Depth 5: a + b + c + d + e
    etc.
    """
    probes = []
    for depth in range(1, max_depth + 1):
        # Use fixed numbers so expected answer is deterministic
        numbers = [str((i * 3 + 7) % 20 + 1) for i in range(depth)]
        expr = " + ".join(numbers)
        expected = str(sum(int(n) for n in numbers))
        probes.append((f"Compute: {expr}. Give ONLY the final number.", expected))
    
    return ProbeSuite(
        domain="addition_depth",
        probes=probes,
        difficulty_levels=[f"depth_{d}" for d in range(1, max_depth + 1)],
    )


# ─── Multiplication Depth Probes ──────────────────────────────────────────────

def multiplication_depth_probes(max_depth: int = 7) -> ProbeSuite:
    """Multiplication chain probes. Smaller numbers to avoid overflow."""
    probes = []
    for depth in range(1, max_depth + 1):
        numbers = [str((i % 3) + 2) for i in range(depth)]  # 2,3,4,2,3,4...
        expr = " × ".join(numbers)
        result = 1
        for n in numbers:
            result *= int(n)
        probes.append((f"Compute: {expr}. Give ONLY the final number.", str(result)))
    
    return ProbeSuite(
        domain="multiplication_depth",
        probes=probes,
        difficulty_levels=[f"depth_{d}" for d in range(1, max_depth + 1)],
    )


# ─── Coefficient Familiarity Probes ───────────────────────────────────────────

def coefficient_probes() -> ProbeSuite:
    """Test how coefficient patterns affect accuracy.

    Key finding (F14): seed-mini has no coefficient blind spot (40/40).
    a²-ab+b² = familiar (Eisenstein norm)
    a²-ab+2b² = still familiar (modified quadratic)
    a²+3ab-5b² = unfamiliar
    """
    return ProbeSuite(
        domain="coefficient_familiarity",
        probes=[
            ("Compute N(5, -3) where N(a,b) = a² - ab + b². Give ONLY the number.", "49"),
            ("Compute N(5, -3) where N(a,b) = a² - ab + 2b². Give ONLY the number.", "58"),
            ("Compute N(5, -3) where N(a,b) = 2a² - 3ab + b². Give ONLY the number.", "68"),
            ("Compute N(5, -3) where N(a,b) = a² + 3ab - 5b². Give ONLY the number.", "-11"),
            ("Compute N(3, 2) where N(a,b) = a² - ab + b². Give ONLY the number.", "7"),
            ("Compute N(7, 4) where N(a,b) = a² - ab + b². Give ONLY the number.", "37"),
            ("Compute N(10, -6) where N(a,b) = a² - ab + b². Give ONLY the number.", "196"),
            ("Compute N(5, -3) where N(a,b) = a³ + ab - b². Give ONLY the number.", "107"),
        ],
        difficulty_levels=[
            "familiar_eisenstein", "familiar_modified", "familiar_wide", "unfamiliar",
            "familiar_small", "familiar_medium", "familiar_large", "unfamiliar_cubic",
        ],
    )


# ─── Syllogism Probes ─────────────────────────────────────────────────────────

def syllogism_probes() -> ProbeSuite:
    """Logical reasoning probes. gemini-lite has ∞ CA here."""
    # NOTE: Yes/no format is TOXIC (F15 — 0/8 for both champions).
    # Use extraction-safe format instead.
    return ProbeSuite(
        domain="syllogism",
        probes=[
            ("All cats are animals. Whiskers is a cat. Therefore Whiskers is a ____. Give ONLY the missing word.", "animal"),
            ("No fish can fly. Salmon are fish. What CAN'T salmon do? Give ONLY the verb.", "fly"),
            ("All roses are flowers. Some flowers fade quickly. Is the conclusion 'all roses fade quickly' VALID or INVALID? Give ONLY one word.", "INVALID"),
            ("If it rains, the ground gets wet. The ground is wet. Can we conclude it rained? Answer DEFINITELY or POSSIBLY. Give ONLY one word.", "POSSIBLY"),
            ("All A are B. All B are C. Therefore all A are ____. Give ONLY the missing letter.", "C"),
        ],
        difficulty_levels=["simple", "negative", "some", "abduction", "transitive"],
    )


# ─── Magnitude Probes ─────────────────────────────────────────────────────────

def magnitude_probes() -> ProbeSuite:
    """Test accuracy vs input magnitude. seed-mini has ∞ CA here."""
    return ProbeSuite(
        domain="magnitude",
        probes=[
            ("What is 3 + 5? Give ONLY the number.", "8"),
            ("What is 37 + 48? Give ONLY the number.", "85"),
            ("What is 456 + 789? Give ONLY the number.", "1245"),
            ("What is 12345 + 67890? Give ONLY the number.", "80235"),
            ("What is 999999 + 1? Give ONLY the number.", "1000000"),
        ],
        difficulty_levels=["tiny", "small", "medium", "large", "huge"],
    )


# ─── Full Calibration Suite ───────────────────────────────────────────────────

def full_suite() -> List[ProbeSuite]:
    """All probe suites for a complete calibration run."""
    return [
        addition_depth_probes(15),
        multiplication_depth_probes(7),
        coefficient_probes(),
        syllogism_probes(),
        magnitude_probes(),
    ]


def quick_suite() -> List[ProbeSuite]:
    """Fast calibration — 20 probes covering key domains."""
    return [
        ProbeSuite("quick_add", addition_depth_probes(5).probes[:5],
                   ["d1","d2","d3","d4","d5"]),
        ProbeSuite("quick_mul", multiplication_depth_probes(4).probes[:4],
                   ["d1","d2","d3","d4"]),
        coefficient_probes(),
        ProbeSuite("quick_syllogism", syllogism_probes().probes[:3],
                   ["simple","negative","some"]),
    ]
