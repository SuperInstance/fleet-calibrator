"""
fleet_calibrator/calibrator.py — Run calibration against model APIs.

Takes a model profile, runs probe suites, measures accuracy,
detects phase transitions, and emits PLATO tiles with results.

This IS the continuous improvement engine. Run periodically:
  - Every 6 hours for fleet champions
  - On new model detection
  - When accuracy anomalies are detected
"""

from __future__ import annotations
import json, time, os, asyncio
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime

from .probes import ProbeSuite, full_suite, quick_suite


@dataclass
class ProbeResult:
    """Result of a single probe."""
    question: str
    expected: str
    actual: str
    correct: bool
    latency_ms: float
    domain: str
    difficulty: str = ""


@dataclass
class CalibrationResult:
    """Complete calibration run for one model."""
    model: str
    provider: str
    timestamp: str
    total_probes: int
    correct: int
    accuracy: float
    results_by_domain: Dict[str, dict] = field(default_factory=dict)
    phase_transitions: List[dict] = field(default_factory=list)
    duration_seconds: float = 0.0
    cost: float = 0.0

    @property
    def status(self) -> str:
        if self.accuracy >= 0.85:
            return "CHAMPION"
        elif self.accuracy >= 0.70:
            return "CONTENDER"
        elif self.accuracy >= 0.50:
            return "BACKUP"
        return "UNRELIABLE"


async def query_model(prompt: str, model_id: str, provider: str,
                      temperature: float = 0.0,
                      max_tokens: int = 50) -> tuple[str, float]:
    """Query a model and return (answer_text, latency_ms)."""
    import httpx

    # Get API key based on provider
    if provider == "deepinfra":
        key_path = os.path.expanduser("~/.openclaw/workspace/.credentials/deepinfra-api-key.txt")
        with open(key_path) as f:
            api_key = f.read().strip()
        url = "https://api.deepinfra.com/v1/openai/chat/completions"
    elif provider == "zai":
        api_key = "703f56774c324a76b8a283ce50b15744.tLKi6d9yeYza5Spg"
        url = "https://api.z.ai/api/coding/paas/v4/chat/completions"
    elif provider == "groq":
        key_path = os.path.expanduser("~/.openclaw/workspace/.credentials/groq-api-key.txt")
        with open(key_path) as f:
            api_key = f.read().strip()
        url = "https://api.groq.com/openai/v1/chat/completions"
    else:
        return "ERROR: unknown provider", 0.0

    system = "Give ONLY the final answer. No explanation, no steps."
    t0 = time.time()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
            )
        latency_ms = (time.time() - t0) * 1000
        data = r.json()

        if r.status_code != 200:
            return f"ERROR: {r.status_code}", latency_ms

        choice = data["choices"][0]["message"]
        content = choice.get("content", "")
        reasoning = choice.get("reasoning_content", "")
        text = content if content.strip() else reasoning

        # Extract last number from response
        import re
        numbers = re.findall(r'-?\d+\.?\d*', text)
        if numbers:
            return numbers[-1], latency_ms

        # Check for yes/no/maybe
        text_lower = text.strip().lower()
        if text_lower in ("yes", "no", "maybe"):
            return text_lower, latency_ms

        return text.strip()[:50], latency_ms

    except Exception as e:
        return f"ERROR: {e}", (time.time() - t0) * 1000


def check_answer(actual: str, expected: str) -> bool:
    """Check if actual answer matches expected.
    
    Handles: exact match, numeric comparison, word-in-answer,
    and negative numbers that models format differently.
    """
    actual_clean = actual.strip().lower()
    expected_clean = expected.strip().lower()

    if actual_clean == expected_clean:
        return True

    # Expected answer appears in actual (for verbose models)
    if expected_clean in actual_clean:
        return True

    # Numeric comparison
    try:
        if abs(float(actual_clean) - float(expected_clean)) < 0.01:
            return True
    except:
        pass

    # Try extracting last number from actual
    import re
    numbers = re.findall(r'-?\d+\.?\d*', actual_clean)
    if numbers:
        try:
            if abs(float(numbers[-1]) - float(expected_clean)) < 0.01:
                return True
        except:
            pass

    return False


async def calibrate_model(model_name: str, model_id: str, provider: str,
                          temperature: float = 0.0,
                          suites: List[ProbeSuite] = None,
                          plato_url: str = "http://147.224.38.131:8847") -> CalibrationResult:
    """Run full calibration on a model."""
    if suites is None:
        suites = full_suite()

    t0 = time.time()
    all_results: List[ProbeResult] = []

    for suite in suites:
        for i, (question, expected) in enumerate(suite.probes):
            actual, latency = await query_model(
                question, model_id, provider, temperature=temperature
            )
            correct = check_answer(actual, expected)
            difficulty = suite.difficulty_levels[i] if i < len(suite.difficulty_levels) else ""

            all_results.append(ProbeResult(
                question=question[:80],
                expected=expected,
                actual=actual[:30],
                correct=correct,
                latency_ms=latency,
                domain=suite.domain,
                difficulty=difficulty,
            ))

    duration = time.time() - t0

    # Analyze by domain
    by_domain: Dict[str, dict] = {}
    for r in all_results:
        if r.domain not in by_domain:
            by_domain[r.domain] = {"total": 0, "correct": 0, "results": []}
        by_domain[r.domain]["total"] += 1
        if r.correct:
            by_domain[r.domain]["correct"] += 1
        by_domain[r.domain]["results"].append({
            "difficulty": r.difficulty,
            "correct": r.correct,
        })

    # Calculate accuracy per domain
    for domain in by_domain:
        total = by_domain[domain]["total"]
        correct = by_domain[domain]["correct"]
        by_domain[domain]["accuracy"] = round(correct / total, 3) if total > 0 else 0.0

    # Detect phase transitions (first failure in ordered sequences)
    transitions = []
    for domain, data in by_domain.items():
        results = data["results"]
        for i, r in enumerate(results):
            if not r["correct"]:
                transitions.append({
                    "domain": domain,
                    "depth": i + 1,
                    "type": "first_failure",
                })
                break

    total_correct = sum(1 for r in all_results if r.correct)
    total_probes = len(all_results)

    result = CalibrationResult(
        model=model_name,
        provider=provider,
        timestamp=datetime.utcnow().isoformat() + "Z",
        total_probes=total_probes,
        correct=total_correct,
        accuracy=round(total_correct / total_probes, 3) if total_probes > 0 else 0.0,
        results_by_domain=by_domain,
        phase_transitions=transitions,
        duration_seconds=round(duration, 1),
    )

    # Emit to PLATO
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{plato_url}/submit",
                json={
                    "room_id": f"calibration-{model_name}",
                    "domain": "fleet-calibration",
                    "agent": "fleet-calibrator",
                    "question": f"Calibration {result.timestamp}",
                    "answer": json.dumps(asdict(result), default=str),
                    "tile_type": "calibration",
                },
            )
    except:
        pass  # PLATO unavailable, still return results

    return result


async def quick_calibrate(model_name: str, model_id: str, provider: str,
                          temperature: float = 0.0) -> CalibrationResult:
    """Fast calibration — ~20 probes, <30 seconds."""
    return await calibrate_model(
        model_name, model_id, provider, temperature, suites=quick_suite()
    )


def format_results(result: CalibrationResult) -> str:
    """Human-readable calibration report."""
    lines = [
        f"═══ Calibration: {result.model} ({result.provider}) ═══",
        f"Time: {result.timestamp}",
        f"Accuracy: {result.correct}/{result.total_probes} = {result.accuracy:.1%}",
        f"Status: {result.status}",
        f"Duration: {result.duration_seconds:.1f}s",
        "",
        "By Domain:",
    ]
    for domain, data in result.results_by_domain.items():
        acc = data.get("accuracy", 0.0)
        bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
        lines.append(f"  {domain:25s} {bar} {acc:.0%}")

    if result.phase_transitions:
        lines.append("")
        lines.append("Phase Transitions:")
        for t in result.phase_transitions:
            lines.append(f"  ⚠ {t['domain']}: first failure at depth {t['depth']}")

    return "\n".join(lines)
