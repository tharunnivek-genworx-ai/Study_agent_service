"""LlamaParse extraction, caching, and persistence for reference materials."""

from src.api.schemas.study_material_schemas.llama_parse_schema import (
    LlamaParseExtractionResult,
    ParseImageRecord,
    load_study_material_schema,
)
from src.api.utils.reference_llamaparse_utils.llama_parse_extractor import (
    compute_pdf_content_hash,
    download_figures,
    extract_structured_reference,
    fetch_structured_data_from_extract_job,
)
from src.api.utils.reference_llamaparse_utils.reference_llamaparse_cache import (
    resolve_reference_extraction,
)
from src.api.utils.reference_llamaparse_utils.reference_llamaparse_persistence import (
    build_parsed_reference_data,
    build_parsed_reference_data_from_extraction,
    persist_reference_llamaparse,
)

__all__ = [
    "LlamaParseExtractionResult",
    "ParseImageRecord",
    "build_parsed_reference_data",
    "build_parsed_reference_data_from_extraction",
    "compute_pdf_content_hash",
    "download_figures",
    "extract_structured_reference",
    "fetch_structured_data_from_extract_job",
    "load_study_material_schema",
    "persist_reference_llamaparse",
    "resolve_reference_extraction",
]
