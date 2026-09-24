"""Business exceptions of the pipeline.

Defining your own exceptions rather than raising generic `Exception`s serves
three purposes:

1. The error message in the Airflow logs immediately says WHICH step failed
   and WHY.
2. You can decide, per error type, whether to retry or to give up (see PHASE 9
   on retries).
3. The tests can check that one precise error is raised, not just any error.
"""


class PipelineError(Exception):
    """Base class: every deliberate pipeline error inherits from it."""


class MissingSourceFileError(PipelineError):
    """An expected source file cannot be found.

    NOT retryable: rerunning will not make the file appear.
    """


class SchemaValidationError(PipelineError):
    """The file exists but its columns do not match the contract.

    NOT retryable: the file structure will not change on its own.
    """


class EmptySourceError(PipelineError):
    """The file exists with the right columns, but holds no rows at all.

    NOT retryable in this project: we prefer failing to loading nothing.
    """


class DataQualityError(PipelineError):
    """The data violates a blocking quality rule.

    NOT retryable: the data is at fault, not the infrastructure.
    """


class LoadError(PipelineError):
    """The database load failed.

    POTENTIALLY retryable: a momentarily unavailable database or a network
    outage often resolves itself.
    """
