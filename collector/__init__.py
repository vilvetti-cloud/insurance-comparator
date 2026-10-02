"""Source collection and verification pipeline for insurance products.

Public pipeline objects are imported lazily so importing a lightweight
submodule such as collector.casco_document does not initialize the database
stack or optional provider dependencies.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .pipeline import CascoCollectionPipeline, PipelineResult

__all__ = ["CascoCollectionPipeline", "PipelineResult"]


def __getattr__(name: str):
    if name in __all__:
        from .pipeline import CascoCollectionPipeline, PipelineResult

        exports = {
            "CascoCollectionPipeline": CascoCollectionPipeline,
            "PipelineResult": PipelineResult,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
