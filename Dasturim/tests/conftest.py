import sys
import os
from pathlib import Path

os.environ.setdefault("DATAFLOW_AUTH_ENABLED", "false")

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
