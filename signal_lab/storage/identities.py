from __future__ import annotations

from hashlib import sha256

from signal_lab.structured_data import canonical_json_bytes


def raw_acquisition_id(
    snapshot_hash: str,
    provider: str,
    resource: str,
    retrieved_at: str,
) -> str:
    """Identify one observation event independently from its content object."""

    return sha256(
        canonical_json_bytes(
            {
                "schema_version": "signal-lab.raw-acquisition.v1",
                "snapshot_hash": snapshot_hash,
                "provider": provider,
                "resource": resource,
                "retrieved_at": retrieved_at,
            }
        )
    ).hexdigest()
