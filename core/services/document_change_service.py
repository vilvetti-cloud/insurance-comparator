from __future__ import annotations

import hashlib
from typing import Any, Iterable


def sha256_bytes(content: bytes) -> str:
    """Return a stable checksum for a downloaded source document."""
    return hashlib.sha256(content).hexdigest()


def build_document_manifest(master: dict[str, Any], checksums: dict[str, str]) -> dict[str, Any]:
    """Bind known official source URLs to checksums without rewriting accepted facts."""
    documents: dict[str, dict[str, Any]] = {}
    for company in master.get("companies", []):
        company_name = company.get("name")
        for field in company.get("fields", []):
            urls = []
            if field.get("source_url"):
                urls.append(field["source_url"])
            elif company.get("source_url"):
                urls.append(company["source_url"])
            for url in urls:
                if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                    continue
                entry = documents.setdefault(url, {"checksum": checksums.get(url), "consumers": []})
                entry["consumers"].append({
                    "company": company_name,
                    "field": field.get("key"),
                    "source_pdfs": field.get("source_pdfs") or company.get("source_pdfs") or [],
                })
    for entry in documents.values():
        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for consumer in entry["consumers"]:
            unique[(str(consumer.get("company")), str(consumer.get("field")))] = consumer
        entry["consumers"] = list(unique.values())
    return {"schema_version": "1.0", "documents": documents}


def plan_incremental_refresh(
    previous: dict[str, Any] | None,
    current_checksums: dict[str, str],
    master: dict[str, Any],
) -> dict[str, Any]:
    """Identify changed official documents and only the condition rows they affect.

    This function intentionally does not mutate the accepted master data. A
    caller must successfully extract and validate changed documents before
    publishing any replacement facts.
    """
    previous_docs = (previous or {}).get("documents", {})
    current_urls = {
        field.get("source_url") or company.get("source_url")
        for company in master.get("companies", [])
        for field in company.get("fields", [])
        if field.get("source_url") or company.get("source_url")
    }
    changed: list[str] = []
    unchanged: list[str] = []
    added: list[str] = []
    for url in sorted(current_urls):
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            continue
        new_hash = current_checksums.get(url)
        old_entry = previous_docs.get(url) or {}
        old_hash = old_entry.get("checksum")
        if not new_hash:
            continue
        if url not in previous_docs:
            added.append(url)
        elif old_hash != new_hash:
            changed.append(url)
        else:
            unchanged.append(url)

    affected: list[dict[str, str]] = []
    target_urls = set(changed + added)
    for company in master.get("companies", []):
        for field in company.get("fields", []):
            url = field.get("source_url") or company.get("source_url")
            if url in target_urls:
                affected.append({"company": company.get("name", ""), "field": field.get("key", ""), "source_url": url})

    return {
        "changed_documents": changed,
        "new_documents": added,
        "unchanged_documents": unchanged,
        "affected_conditions": affected,
        "affected_condition_count": len(affected),
        "requires_extraction": bool(changed or added),
    }


def manifest_from_plan(master: dict[str, Any], checksums: dict[str, str]) -> dict[str, Any]:
    """Create the manifest to persist after a successful refresh/check cycle."""
    return build_document_manifest(master, checksums)
