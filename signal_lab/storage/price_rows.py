from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from signal_lab.storage.sql import CatalogConnection
from signal_lab.storage.codec import iso, json_dumps


def is_external_project_reference(provider: str, metadata: dict[str, Any]) -> bool:
    serialized = json_dumps(metadata).casefold()
    return (
        provider.casefold().startswith("heimdall")
        or "\\\\heimdall\\\\" in serialized
        or "/heimdall/" in serialized
    )


def save_price_snapshot_row(
    connection: CatalogConnection,
    snapshot: Any,
    coverage_issues: Sequence[dict[str, Any]],
) -> None:
    snapshot_hash = snapshot.snapshot_hash
    scope = (
        snapshot.instrument.canonical_code,
        snapshot.timeframe,
        snapshot.provider,
        snapshot.requested_start.isoformat(),
        snapshot.requested_end.isoformat(),
    )
    normalized_issues = tuple(
        sorted(
            (
                str(issue["type"]),
                iso(issue.get("date", "")) if issue.get("date") else "",
                str(issue.get("detail", "")),
            )
            for issue in coverage_issues
        )
    )
    existing_snapshot = connection.execute(
        "SELECT * FROM price_snapshots WHERE snapshot_hash = ?", (snapshot_hash,),
    ).fetchone()
    current = connection.execute(
        """
        SELECT retrieved_at, snapshot_hash FROM price_snapshots
        WHERE canonical_code = ? AND timeframe = ? AND provider = ?
          AND requested_start = ? AND requested_end = ? AND is_latest = 1
        """,
        scope,
    ).fetchone()
    promote = current is None or snapshot.retrieved_at >= datetime.fromisoformat(
        current["retrieved_at"].replace("Z", "+00:00")
    )
    connection.execute(
        """
        INSERT INTO price_snapshots(
            snapshot_hash, canonical_code, timeframe, provider, provider_symbol,
            requested_start, requested_end, actual_start, actual_end, retrieved_at,
            source_snapshot_hash, price_basis, coverage_status, row_count,
            metadata_json, is_latest, identity_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(snapshot_hash) DO NOTHING
        """,
        (
            snapshot_hash,
            snapshot.instrument.canonical_code,
            snapshot.timeframe,
            snapshot.provider,
            snapshot.provider_symbol,
            snapshot.requested_start.isoformat(),
            snapshot.requested_end.isoformat(),
            snapshot.actual_start.isoformat() if snapshot.actual_start else None,
            snapshot.actual_end.isoformat() if snapshot.actual_end else None,
            snapshot.retrieved_at.isoformat(),
            snapshot.source_snapshot_hash,
            snapshot.price_basis,
            snapshot.coverage_status,
            len(snapshot.bars),
            json_dumps(snapshot.metadata),
            snapshot.identity_version,
        ),
    )
    if existing_snapshot is None:
        connection.executemany(
            """
            INSERT INTO price_bars(
                snapshot_hash, observed_at, observation_date, open, high, low, close,
                adjusted_close, volume, dividend, split_factor
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_hash,
                    bar.observed_at.isoformat(),
                    bar.observation_date.isoformat(),
                    bar.open,
                    bar.high,
                    bar.low,
                    bar.close,
                    bar.adjusted_close,
                    bar.volume,
                    bar.dividend,
                    bar.split_factor,
                )
                for bar in snapshot.bars
            ],
        )
        connection.executemany(
            """
            INSERT INTO coverage_issues(snapshot_hash, issue_type, issue_date, detail)
            VALUES (?, ?, ?, ?)
            """,
            [
                (snapshot_hash, issue_type, issue_date, detail)
                for issue_type, issue_date, detail in normalized_issues
            ],
        )
    else:
        _verify_immutable_snapshot(connection, snapshot, normalized_issues)
    if promote:
        connection.execute(
            """
            UPDATE price_snapshots SET is_latest = 0
            WHERE canonical_code = ? AND timeframe = ? AND provider = ?
              AND requested_start = ? AND requested_end = ?
            """,
            scope,
        )
        connection.execute(
            "UPDATE price_snapshots SET is_latest = 1 WHERE snapshot_hash = ?",
            (snapshot_hash,),
        )


def _verify_immutable_snapshot(
    connection: CatalogConnection,
    snapshot: Any,
    coverage_issues: tuple[tuple[str, str, str], ...],
) -> None:
    row = connection.execute(
        "SELECT * FROM price_snapshots WHERE snapshot_hash = ?",
        (snapshot.snapshot_hash,),
    ).fetchone()
    expected = {
        "canonical_code": snapshot.instrument.canonical_code,
        "timeframe": snapshot.timeframe,
        "provider": snapshot.provider,
        "provider_symbol": snapshot.provider_symbol,
        "requested_start": snapshot.requested_start.isoformat(),
        "requested_end": snapshot.requested_end.isoformat(),
        "actual_start": snapshot.actual_start.isoformat() if snapshot.actual_start else None,
        "actual_end": snapshot.actual_end.isoformat() if snapshot.actual_end else None,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "source_snapshot_hash": snapshot.source_snapshot_hash,
        "price_basis": snapshot.price_basis,
        "coverage_status": snapshot.coverage_status,
        "row_count": len(snapshot.bars),
        "metadata_json": json_dumps(snapshot.metadata),
        "identity_version": snapshot.identity_version,
    }
    mismatches = [key for key, value in expected.items() if row[key] != value]
    stored_bars = tuple(
        tuple(item)
        for item in connection.execute(
            """
            SELECT observed_at, observation_date, open, high, low, close, adjusted_close,
                   volume, dividend, split_factor
            FROM price_bars WHERE snapshot_hash = ? ORDER BY observed_at
            """,
            (snapshot.snapshot_hash,),
        ).fetchall()
    )
    expected_bars = tuple(
        (
            bar.observed_at.isoformat(), bar.observation_date.isoformat(), bar.open, bar.high,
            bar.low, bar.close, bar.adjusted_close, bar.volume, bar.dividend, bar.split_factor,
        )
        for bar in snapshot.bars
    )
    stored_issues = tuple(
        tuple(item)
        for item in connection.execute(
            """
            SELECT issue_type, issue_date, detail FROM coverage_issues
            WHERE snapshot_hash = ? ORDER BY issue_type, issue_date, detail
            """,
            (snapshot.snapshot_hash,),
        ).fetchall()
    )
    if mismatches or stored_bars != expected_bars or stored_issues != coverage_issues:
        detail = ", ".join(mismatches) or "bars or coverage issues"
        raise ValueError(
            f"immutable price snapshot content mismatch for {snapshot.snapshot_hash}: {detail}"
        )
