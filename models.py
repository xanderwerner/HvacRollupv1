"""The Lead data model (stdlib dataclass — zero dependency)."""
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Lead:
    # identity / provenance
    place_id: str
    company_name: str
    trade_type: str           # HVAC | Plumbing | Electrical
    city: str
    discovery_source: str = "Google Maps"

    # company info
    business_address: str = ""
    website: str = ""
    business_phone: str = ""   # main line — NOT owner mobile; goes in Notes
    business_status: str = ""

    # size signals (Google Places)
    review_count: Optional[int] = None
    rating: Optional[float] = None

    # pipeline state
    research_stage: str = "New"        # New until a human claims it
    disqualify_reason: str = ""
    buy_box_fit: str = ""              # Strong | Possible | Weak
    priority_tier: str = ""           # capped at B in v1
    survived_filter: bool = True

    def as_dict(self) -> dict:
        return asdict(self)
