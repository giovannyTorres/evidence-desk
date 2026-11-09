"""Run the isolated semantic benchmark without requiring a PYTHONPATH setting."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'services' / 'api'))
from evidence.ontology_runner import main  # noqa: E402

if __name__ == '__main__':
    main()
