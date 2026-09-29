"""Transaction ingestion: one contract, many sources."""

from .base import (  # noqa: F401
    IngestResult,
    SourceStatus,
    TransactionSource,
    all_sources,
    get_source,
    register,
)
from . import csv_source  # noqa: F401  (registers CsvSource)
from . import pdf_source  # noqa: F401  (registers PdfSource)
from . import plaid_source  # noqa: F401  (registers PlaidSource)
from .csv_source import parse_csv  # noqa: F401
from .pdf_source import parse_statement  # noqa: F401
