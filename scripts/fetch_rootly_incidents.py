#!/usr/bin/env python3
"""Fetch Rootly incidents and write Doom WASM incident TSV.

The Rootly API token is read from ROOTLY_API_TOKEN and is only sent as an
Authorization header. It is never written to disk or printed.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOTLY_INCIDENTS_URL = "https://api.rootly.com/v1/incidents"

SEVERITY_TO_MOBJ = {
    "SEV0": "MT_BRUISER",
    "SEV1": "MT_SHADOWS",
    "SEV2": "MT_SERGEANT",
    "SEV3": "MT_TROOP",
    "SEV4": "MT_SHOTGUY",
    "SEV5": "MT_POSSESSED",
}

SEVERITY_ALIASES = {
    "sev0": "SEV0",
    "sev 0": "SEV0",
    "sev-0": "SEV0",
    "severity 0": "SEV0",
    "critical": "SEV0",
    "sev1": "SEV1",
    "sev 1": "SEV1",
    "sev-1": "SEV1",
    "severity 1": "SEV1",
    "major": "SEV1",
    "sev2": "SEV2",
    "sev 2": "SEV2",
    "sev-2": "SEV2",
    "severity 2": "SEV2",
    "partial degradation": "SEV2",
    "sev3": "SEV3",
    "sev 3": "SEV3",
    "sev-3": "SEV3",
    "severity 3": "SEV3",
    "minor": "SEV3",
    "sev4": "SEV4",
    "sev 4": "SEV4",
    "sev-4": "SEV4",
    "severity 4": "SEV4",
    "low": "SEV4",
    "sev5": "SEV5",
    "sev 5": "SEV5",
    "sev-5": "SEV5",
    "severity 5": "SEV5",
    "informational": "SEV5",
    "planned": "SEV5",
}

SEVERITY_SORT = {
    "SEV0": 0,
    "SEV1": 1,
    "SEV2": 2,
    "SEV3": 3,
    "SEV4": 4,
    "SEV5": 5,
}

TSV_COLUMNS = [
    "severity",
    "mobj_type",
    "label",
    "rootly_id",
    "rootly_url",
    "created_at",
    "status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Rootly incidents and write Doom WASM TSV."
    )
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--time-field", default="created_at")
    parser.add_argument("--max-incidents", type=int, default=24)
    parser.add_argument("--output", default="src/rootly_incidents.local.tsv")
    return parser.parse_args()


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_output_path(output: str) -> Path:
    path = Path(output)
    if path.is_absolute():
        return path
    return repo_root() / path


def isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "doom-wasm-rootly-ingest/1.0",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read().decode(charset)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Rootly API request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Rootly API request failed: {exc.reason}") from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Rootly API returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Rootly API returned an unexpected response shape")

    return data


def initial_url(args: argparse.Namespace) -> str:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=args.lookback_days)
    params = {
        f"filter[{args.time_field}][gte]": isoformat_z(start),
        f"filter[{args.time_field}][lte]": isoformat_z(now),
        "page[size]": "100",
    }
    return f"{ROOTLY_INCIDENTS_URL}?{urllib.parse.urlencode(params)}"


def next_link(response_json: dict[str, Any]) -> str | None:
    links = response_json.get("links")
    if not isinstance(links, dict):
        return None

    value = links.get("next")
    if value in (None, ""):
        return None

    if isinstance(value, str):
        return urllib.parse.urljoin(ROOTLY_INCIDENTS_URL, value)

    if isinstance(value, dict):
        href = value.get("href")
        if isinstance(href, str) and href:
            return urllib.parse.urljoin(ROOTLY_INCIDENTS_URL, href)

    return None


def normalize_key(value: str) -> str:
    cleaned = value.strip().lower()
    cleaned = cleaned.replace("_", "-")
    cleaned = " ".join(cleaned.split())
    return cleaned


def canonical_severity(raw_values: list[str]) -> str:
    for raw in raw_values:
        if not raw:
            continue

        key = normalize_key(raw)
        if key in SEVERITY_ALIASES:
            return SEVERITY_ALIASES[key]

        compact = key.replace("-", "").replace(" ", "")
        if compact in SEVERITY_ALIASES:
            return SEVERITY_ALIASES[compact]

    return "SEV5"


def nested_dict(value: Any, *keys: str) -> dict[str, Any]:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def severity_values(attributes: dict[str, Any]) -> list[str]:
    severity = attributes.get("severity")
    values: list[str] = []

    if isinstance(severity, str):
        values.append(severity)

    if isinstance(severity, dict):
        attrs = nested_dict(severity, "data", "attributes")
        for key in ("slug", "name", "severity", "label"):
            value = attrs.get(key)
            if isinstance(value, str):
                values.append(value)

        for key in ("slug", "name", "severity", "label"):
            value = severity.get(key)
            if isinstance(value, str):
                values.append(value)

    for key in ("severity", "severity_name", "severity_slug"):
        value = attributes.get(key)
        if isinstance(value, str):
            values.append(value)

    return values


def sanitize_text(value: Any, max_chars: int | None = None) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    text = text.encode("ascii", "replace").decode("ascii")

    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip()

    return text


def incident_url(incident: dict[str, Any], attributes: dict[str, Any]) -> str:
    for value in (attributes.get("url"), attributes.get("short_url"), incident.get("url")):
        if isinstance(value, str) and value:
            return sanitize_text(value)
    return ""


def normalize_incident(incident: dict[str, Any]) -> dict[str, str]:
    attributes = incident.get("attributes")
    if not isinstance(attributes, dict):
        attributes = {}

    severity = canonical_severity(severity_values(attributes))
    title = sanitize_text(attributes.get("title") or incident.get("id") or "incident")
    label = sanitize_text(f"{severity}: {title}", max_chars=64)

    return {
        "severity": severity,
        "mobj_type": SEVERITY_TO_MOBJ[severity],
        "label": label,
        "rootly_id": sanitize_text(incident.get("id")),
        "rootly_url": incident_url(incident, attributes),
        "created_at": sanitize_text(attributes.get("created_at")),
        "status": sanitize_text(attributes.get("status")),
    }


def fetch_incidents(args: argparse.Namespace, token: str) -> list[dict[str, str]]:
    url = initial_url(args)
    incidents: list[dict[str, str]] = []

    while url:
        response = request_json(url, token)
        data = response.get("data")

        if not isinstance(data, list):
            raise RuntimeError("Rootly API response did not include a data list")

        for item in data:
            if isinstance(item, dict):
                incidents.append(normalize_incident(item))

        url = next_link(response)

    incidents.sort(
        key=lambda item: (
            SEVERITY_SORT.get(item["severity"], 99),
            -parse_datetime_sort_value(item["created_at"]),
        )
    )

    return incidents[: args.max_incidents]


def parse_datetime_sort_value(value: str) -> float:
    if not value:
        return 0.0

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0.0

    return parsed.timestamp()


def write_tsv(output_path: Path, incidents: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=TSV_COLUMNS,
            dialect="excel-tab",
            lineterminator="\n",
        )
        writer.writeheader()
        for incident in incidents:
            writer.writerow(incident)


def main() -> int:
    args = parse_args()
    token = os.environ.get("ROOTLY_API_TOKEN")

    if not token:
        print(
            "ERROR: ROOTLY_API_TOKEN is required to fetch Rootly incidents.",
            file=sys.stderr,
        )
        return 2

    if args.lookback_days < 1:
        print("ERROR: --lookback-days must be >= 1.", file=sys.stderr)
        return 2

    if args.max_incidents < 1:
        print("ERROR: --max-incidents must be >= 1.", file=sys.stderr)
        return 2

    try:
        incidents = fetch_incidents(args, token)
        output_path = resolve_output_path(args.output)
        write_tsv(output_path, incidents)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {len(incidents)} incident(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
