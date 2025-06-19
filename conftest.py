"""Global pytest configuration.

Ensures that the project root (where *models.py*, *storage.py*, etc. live)
exists on ``sys.path`` so that absolute imports inside tests work
regardless of the directory pytest started collection from.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Path of this file's parent directory (project root)
PROJECT_ROOT = Path(__file__).resolve().parent

# Insert project root at the beginning of sys.path if not already present.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT)) 