"""Shared test setup — put the repo root on sys.path so `config`, `src.*`
import cleanly whether pytest is run from the root or the tests/ folder."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
