import os
import sys

# Make `import nova...` work when running pytest from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
