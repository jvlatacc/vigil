"""``python -m services.warden`` — run the Warden edge process."""

import sys

from services.warden.main import main

if __name__ == "__main__":
    sys.exit(main())
