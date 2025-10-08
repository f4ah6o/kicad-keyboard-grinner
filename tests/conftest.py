# SPDX-License-Identifier: MIT
"""pytest configuration for keyboard_grinner tests"""

import sys
from pathlib import Path

# Add src directory to path for importing the module under test
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
