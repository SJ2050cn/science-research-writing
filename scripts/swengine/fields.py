"""Validation of the classifier fields passed to `start` (the markup is code's alone)."""
from . import errors

NAMES = ("section", "mode", "samples")


def validate(values, sample_files, data):
    """values: dict of the fields; None means "not given" (the classifier decides).
    Returns it unchanged or raises EngineError."""
    for name in NAMES:
        if values[name] is None:
            continue
        allowed = data["fields"][name]
        if values[name] not in allowed:
            raise errors.EngineError(
                errors.INVALID_FIELDS,
                "%s=%r is not allowed; choose one of: %s" % (name, values[name], ", ".join(allowed)))
    if values["samples"] == "yes" and not sample_files:
        raise errors.EngineError(errors.INVALID_FIELDS, "samples=yes needs at least one --sample-file")
    if values["samples"] == "no" and sample_files:
        raise errors.EngineError(errors.INVALID_FIELDS, "--sample-file given but samples=no")
    return values
