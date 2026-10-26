import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from warmpath import db  # noqa: E402

db.init()
