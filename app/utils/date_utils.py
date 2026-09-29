"""
app/utils/date_utils.py
Date manipulation and calculation utilities for warranty evaluation (FR viii, xvi).
"""
from datetime import datetime, date, timedelta
from typing import Optional, Union


def compute_product_age_days(purchase_date: Union[date, datetime, str], reference_date: Optional[Union[date, datetime]] = None) -> int:
    """Calculate the age of a product in days from purchase to reference date (default: today)."""
    if isinstance(purchase_date, str):
        purchase_date = parse_date_flexible(purchase_date)
    elif isinstance(purchase_date, datetime):
        purchase_date = purchase_date.date()

    if reference_date is None:
        ref = date.today()
    elif isinstance(reference_date, datetime):
        ref = reference_date.date()
    else:
        ref = reference_date

    return max(0, (ref - purchase_date).days)


def compute_remaining_warranty_days(expiry_date: Union[date, datetime, str], reference_date: Optional[Union[date, datetime]] = None) -> int:
    """Calculate remaining warranty days. Can be negative if expired."""
    if isinstance(expiry_date, str):
        expiry_date = parse_date_flexible(expiry_date)
    elif isinstance(expiry_date, datetime):
        expiry_date = expiry_date.date()

    if reference_date is None:
        ref = date.today()
    elif isinstance(reference_date, datetime):
        ref = reference_date.date()
    else:
        ref = reference_date

    return (expiry_date - ref).days


def is_within_reporting_period(fault_date: Union[date, datetime, str], claim_date: Union[date, datetime, str], max_days: int = 30) -> bool:
    """Check if claim was reported within allowed window from fault occurrence."""
    if isinstance(fault_date, str):
        fault_date = parse_date_flexible(fault_date)
    elif isinstance(fault_date, datetime):
        fault_date = fault_date.date()

    if isinstance(claim_date, str):
        claim_date = parse_date_flexible(claim_date)
    elif isinstance(claim_date, datetime):
        claim_date = claim_date.date()

    diff = (claim_date - fault_date).days
    return 0 <= diff <= max_days


def parse_date_flexible(date_str: str) -> date:
    """
    Parse a date string across various common international and receipt formats:
    YYYY-MM-DD, DD/MM/YYYY, MM/DD/YYYY, DD-MM-YYYY, Month DD YYYY, etc.
    """
    if not date_str or not isinstance(date_str, str):
        raise ValueError(f"Invalid date string: {date_str}")

    cleaned = date_str.strip()
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unable to parse date string '{date_str}' with known formats.")
