from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Company:
    id: Optional[int]
    name: str
    slug: str
    official_url: Optional[str] = None
    status: str = "active"


@dataclass(frozen=True)
class Product:
    id: Optional[int]
    company_id: int
    name: str
    slug: str
    product_type: str = "insurance"
    status: str = "active"


@dataclass(frozen=True)
class ComparisonField:
    id: Optional[int]
    product_id: int
    key: str
    label: str
    data_type: str = "text"
    category: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


@dataclass(frozen=True)
class Condition:
    id: Optional[int]
    field_id: int
    value: Optional[str]
    verification_status: str = "unverified"
    checked_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None


@dataclass(frozen=True)
class Source:
    id: Optional[int]
    company_id: int
    url: str
    source_type: str = "official_site"
    title: Optional[str] = None
    status: str = "active"
    last_checked_at: Optional[datetime] = None


@dataclass(frozen=True)
class Document:
    id: Optional[int]
    source_id: int
    document_url: str
    title: Optional[str] = None
    document_date: Optional[str] = None
    document_version: Optional[str] = None
    checksum: Optional[str] = None


@dataclass(frozen=True)
class Evidence:
    id: Optional[int]
    condition_id: int
    source_id: Optional[int] = None
    document_id: Optional[int] = None
    page_number: Optional[int] = None
    text_fragment: Optional[str] = None
    verification_status: str = "unverified"
    verified_at: Optional[datetime] = None
    verified_by: Optional[str] = None
