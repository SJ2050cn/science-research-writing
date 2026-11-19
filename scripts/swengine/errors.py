"""One exit code per failure kind. Success is 0; argparse usage errors are 2."""

USAGE = 2          # reserved for argparse
INVALID_FIELDS = 3  # value outside a closed list, or an impossible combination
RUN = 4            # no such run, run not open, run folder unreadable
MALFORMED = 5      # a submitted result failed validation (stdout still has the step)
INPUT = 8          # input file missing or unreadable
OPEN_RUN = 9       # start refused: the project already has an open run (resume or abandon it)
LOG_FOLDER = 10    # the project's .agents/log folder cannot be created or written (sandbox)
PROFILE = 20       # a profile write or profile workflow was refused (nothing was written)


class EngineError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class Malformed(Exception):
    """A submitted result was refused; the same step is returned with the message (exit MALFORMED)."""
