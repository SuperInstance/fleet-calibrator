#!/usr/bin/env python3
"""Run a quick calibration on fleet champions."""
import asyncio
from fleet_calibrator import quick_calibrate, format_results


async def main():
    models = [
        ("seed-2.0-mini", "ByteDance/Seed-2.0-mini", "deepinfra", 0.0),
        ("gemini-flash-lite", "google/gemini-3.1-flash-lite", "deepinfra", 0.0),
    ]

    print("═══ Fleet Quick Calibration ═══\n")
    for name, model_id, provider, temp in models:
        print(f"Calibrating {name}...")
        result = await quick_calibrate(name, model_id, provider, temp)
        print(format_results(result))
        print()

    print("Done. Results emitted to PLATO.")


if __name__ == "__main__":
    asyncio.run(main())
