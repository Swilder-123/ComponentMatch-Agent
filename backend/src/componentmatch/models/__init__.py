"""The agreed six tables. Importing models never creates a database."""

from componentmatch.models.base import Base
from componentmatch.models.catalog import (
    Component,
    DemoMetadata,
    Offer,
    PerformanceRecord,
    Supplier,
    SupplierCertification,
)

__all__ = [
    "Base",
    "Component",
    "DemoMetadata",
    "Offer",
    "PerformanceRecord",
    "Supplier",
    "SupplierCertification",
]
