# Learnings - Cognitive Architecture Refactor

## Baseline
- 49 V4 tests pass (30 state_machine + 19 detectors)
- Test baseline: ~1282 total tests (full suite times out at 120s, run subset)

## T2: Detector Test Coverage (2026-03-23)
- Created shared test factory: `tests/fixtures/state_machine_helpers.py` (make_candle/make_features/make_context)
- Added 10 positive + 10 negative tests for: TEST, UTA, SO, mSOS, MSOS, BU (accumulation) + AR_DIST, ST_DIST, UT, mSOW (distribution)
- Added 2 evidences tests (accumulation + distribution) to verify non-empty evidences on positive detection
- All 22 detectors now have ≥1 positive test. Total: 41 passed (was 19)
- Detector confidence thresholds vary: PS/SC/AR/ST/TEST/UTA/SO/LPS/mSOS/BU use ≥0.2, SC/MSOS/JOC/BC/UTAD/MSOW use ≥0.3
- Key pattern: each detector checks 3-4 independent conditions → additive confidence → threshold gate → NodeScore|None
- Existing `_candle()/_features()/_context()` helpers in test file kept as-is (test file already had them), shared helpers are for future use
