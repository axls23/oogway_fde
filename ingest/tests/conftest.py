import sys
from pathlib import Path

# ingest.py, chunker.py, transcript.py, db.py, embeddings.py, subset.py are
# flat modules in ingest/, not a package -- make them importable regardless
# of the directory pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
