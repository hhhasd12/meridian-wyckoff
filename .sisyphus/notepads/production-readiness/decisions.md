# Decisions - Production Readiness

## Architecture Decisions
- Model A for leverage: Size field represents leveraged quantity, PnL formula unchanged
- Event name: Use system.shutdown (fix app.py, not position_manager)
- Windows: Use os.replace() for atomic writes
