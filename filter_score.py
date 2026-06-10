"""The filter gate + scoring (pure functions — no network).

Encodes the buy-box rules from the Organic Legend. In v1 the only hard
financial/size signal we have for free is the Google review count, so that
(plus operational status) is the automated gate. Age / PE / truck checks are
left for ROC/ACC enrichment and human review (v2).
"""
import config
from models import Lead


def apply_filter(lead: Lead) -> Lead:
    """Set survived_filter + disqualify_reason from free signals."""
    rc = lead.review_count

    if lead.business_status and lead.business_status != "OPERATIONAL":
        lead.survived_filter = False
        lead.disqualify_reason = "Distressed"  # closed / temporarily closed
        lead.research_stage = "Disqualified"
        return lead

    if rc is None or rc < config.MIN_REVIEWS:
        lead.survived_filter = False
        lead.disqualify_reason = "Too small"
        lead.research_stage = "Disqualified"
        return lead

    if rc > config.MAX_REVIEWS:
        # Not auto-killed — the Legend says verify first (may be too big / PE).
        lead.survived_filter = False
        lead.disqualify_reason = "Too big"
        lead.research_stage = "Disqualified"
        return lead

    lead.survived_filter = True
    return lead


def score(lead: Lead) -> Lead:
    """Assign Buy Box Fit + Priority Tier from available free data.

    Honest v1 limits:
      - No motivation / contact data, so Priority Tier is CAPPED at B.
      - Buy Box Fit is a size/quality proxy only.
    """
    rc = lead.review_count or 0
    rating = lead.rating or 0.0

    # mid-range review volume + solid rating = best free-data proxy for a
    # right-sized, healthy operator.
    if 60 <= rc <= 400 and rating >= 4.3:
        lead.buy_box_fit = "Strong"
        lead.priority_tier = "B — email first"
    elif rating >= 4.0:
        lead.buy_box_fit = "Possible"
        lead.priority_tier = "B — email first"
    else:
        lead.buy_box_fit = "Possible"
        lead.priority_tier = "C — drip only"
    return lead
