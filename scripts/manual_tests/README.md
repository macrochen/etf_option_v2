# Manual Test Scripts

This directory contains ad hoc verification and debugging scripts.

- `test_*.py`: data source probes and one-off validation scripts
- `debug_*.py`: focused debugging scripts for specific modules or symbols
- `verify_*.py`: manual verification scripts for service behavior

These files are not automated unit tests and are not part of a pytest suite.
Run them from the project root or directly by path, for example:

```bash
python scripts/manual_tests/verify_prices.py
```
