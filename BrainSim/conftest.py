import sys
from pathlib import Path

# Make `brainsim` importable when pytest is invoked from the ASHURA repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
