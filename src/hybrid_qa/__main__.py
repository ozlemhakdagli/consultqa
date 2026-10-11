"""Allow `python -m hybrid_qa`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
