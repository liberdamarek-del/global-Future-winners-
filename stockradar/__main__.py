import os
import sys

from stockradar.cli import main

try:
    sys.exit(main())
except BrokenPipeError:  # výstup přesměrovaný do `head` apod.
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)
