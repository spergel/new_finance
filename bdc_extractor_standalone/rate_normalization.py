#!/usr/bin/env python3
"""
Shared helpers for parsing and normalizing interest rate information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from standardization import standardize_reference_rate


@dataclass
class RateComponents:
    """Normalized representation of rate-related attributes."""

    reference_rate: Optional[str] = None
    spread: Optional[str] = None
    floor_rate: Optional[str] = None
    pik_rate: Optional[str] = None
    summary: Optional[str] = None

    def apply_to(self, target: dict) -> None:
        if self.reference_rate is not None:
            target["reference_rate"] = self.reference_rate
        if self.spread is not None:
            target["spread"] = self.spread
        if self.floor_rate is not None:
            target["floor_rate"] = self.floor_rate
        if self.pik_rate is not None:
            target["pik_rate"] = self.pik_rate
        if self.summary is not None:
            target["interest_rate"] = self.summary


def clean_percentage(value: Optional[str | float | int]) -> Optional[str]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        text = str(value).strip()
        if text in {"", "-", "—", "N/A", "n/a"}:
            return None

        text = text.replace("−", "-")
        is_basis_points = "bp" in text.lower()
        cleaned = text.replace(",", "")
        match = re.search(r"([+\-]?)\s*(\d+\.?\d*)", cleaned)
        if not match:
            return None
        sign = match.group(1) or ""
        numeric = float(match.group(2))
        if sign.strip() == "-":
            numeric = -numeric
        if is_basis_points or numeric > 1000:
            numeric /= 100.0

    formatted = f"{numeric:.2f}".rstrip("0").rstrip(".")
    if formatted == "-0":
        formatted = "0"
    return f"{formatted}%"


def normalize_reference(rate_str: Optional[str]) -> Optional[str]:
    if not rate_str:
        return None

    rate_str = rate_str.strip()
    if rate_str in {"", "-", "—", "N/A", "n/a"}:
        return None

    term = None
    paren_match = re.match(r"^([^()]+)\(([^)]+)\)\s*$", rate_str)
    if paren_match:
        rate_str = paren_match.group(1).strip()
        term = paren_match.group(2).strip()

    leading_term_match = re.match(r"^((?:\d+\s*-\s*month|\d+\s*month)\s+)(.+)$", rate_str, re.IGNORECASE)
    if leading_term_match:
        term = leading_term_match.group(1).strip()
        rate_str = leading_term_match.group(2).strip()

    normalized = standardize_reference_rate(rate_str) or rate_str.strip().upper()
    display_map = {
        "PRIME": "Prime",
        "BASE RATE": "Base Rate",
        "FED FUNDS": "Fed Funds",
    }
    display = display_map.get(normalized, normalized)

    if term:
        digits = re.search(r"\d+", term)
        normalized_term = f"{digits.group(0)}-month" if digits else term.strip()
        return f"{display} ({normalized_term})"

    return display


def parse_interest_text(text: str) -> RateComponents:
    components = RateComponents()
    if not text:
        return components

    reference_pattern = re.compile(
        r"((?P<term>\d+\s*-\s*month|\d+\s*month)\s+)?(?P<rate>SOFR|LIBOR|PRIME|EURIBOR|FED\s+FUNDS|FEDERAL\s+FUNDS|CDOR|BASE\s+RATE)",
        re.IGNORECASE,
    )
    reference_match = reference_pattern.search(text)
    if reference_match:
        term = reference_match.group("term")
        rate = reference_match.group("rate")
        normalized_rate = normalize_reference(rate)
        if normalized_rate:
            if term and "(" not in normalized_rate:
                digits = re.search(r"\d+", term)
                term_display = f"{digits.group(0)}-month" if digits else term.strip()
                components.reference_rate = f"{normalized_rate} ({term_display})"
            else:
                components.reference_rate = normalized_rate

        after_reference = text[reference_match.end() :]
        spread_match = re.search(r"([+\-]\s*\d+\.?\d*)\s*%", after_reference)
        if spread_match:
            components.spread = clean_percentage(spread_match.group(0))

    floor_match = re.search(r"floor(?:\s+rate)?(?:\s*[:=])?\s*(-?\d+\.?\d*)\s*%", text, re.IGNORECASE)
    if floor_match:
        components.floor_rate = clean_percentage(floor_match.group(1))

    pik_match = re.search(r"pi?k(?:\s+interest|\s+rate)?(?:\s*[:=])?\s*(-?\d+\.?\d*)\s*%", text, re.IGNORECASE)
    if pik_match:
        components.pik_rate = clean_percentage(pik_match.group(1))

    return components


def compose_summary(reference_rate: Optional[str], spread: Optional[str], floor_rate: Optional[str], pik_rate: Optional[str]) -> Optional[str]:
    parts: list[str] = []
    if reference_rate and spread:
        if spread.startswith("-"):
            parts.append(f"{reference_rate} - {spread[1:]}")
        else:
            parts.append(f"{reference_rate} + {spread}")
    elif reference_rate:
        parts.append(reference_rate)
    elif spread:
        parts.append(spread)

    if floor_rate:
        parts.append(f"Floor {floor_rate}")
    if pik_rate:
        parts.append(f"PIK {pik_rate}")

    if parts:
        return ", ".join(parts)
    return None


def normalize_interest_fields(
    *,
    raw_texts: Iterable[str],
    reference_rate: Optional[str] = None,
    spread: Optional[str] = None,
    floor_rate: Optional[str] = None,
    pik_rate: Optional[str] = None,
    interest_rate: Optional[str] = None,
) -> RateComponents:
    texts = [t for t in raw_texts if t]
    ref = normalize_reference(reference_rate) if reference_rate else None
    spread_clean = clean_percentage(spread)
    floor_clean = clean_percentage(floor_rate)
    pik_clean = clean_percentage(pik_rate)
    summary = None

    for text in texts:
        parsed = parse_interest_text(text)
        if parsed.reference_rate and not ref:
            ref = parsed.reference_rate
        if parsed.spread and not spread_clean:
            spread_clean = parsed.spread
        if parsed.floor_rate and not floor_clean:
            floor_clean = parsed.floor_rate
        if parsed.pik_rate and not pik_clean:
            pik_clean = parsed.pik_rate

    summary = interest_rate
    if not summary:
        summary = compose_summary(ref, spread_clean, floor_clean, pik_clean)

    return RateComponents(
        reference_rate=ref,
        spread=spread_clean,
        floor_rate=floor_clean,
        pik_rate=pik_clean,
        summary=summary,
    )


