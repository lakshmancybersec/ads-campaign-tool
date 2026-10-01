from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.performance import PerformanceSnapshot
from app.services.recommendations import WeeklyRecommendation, build_recommendations


def weekly_summary(db: Session, start_date: date, end_date: date) -> dict:
    snapshots = list(db.scalars(select(PerformanceSnapshot).where(
        PerformanceSnapshot.snapshot_date >= start_date, PerformanceSnapshot.snapshot_date <= end_date
    )))
    totals = defaultdict(float)
    for snapshot in snapshots:
        totals["spend_inr"] += snapshot.spend_inr
        totals["reach"] += snapshot.reach
        totals["impressions"] += snapshot.impressions
        totals["clicks"] += snapshot.clicks
        totals["conversations"] += snapshot.conversations or 0
        totals["leads"] += snapshot.leads
        totals["qualified_leads"] += snapshot.qualified_leads
        totals["sales"] += snapshot.sales
        totals["revenue_inr"] += snapshot.revenue_inr
    totals["ctr"] = (totals["clicks"] / totals["impressions"] * 100) if totals["impressions"] else None
    totals["cpc_inr"] = (totals["spend_inr"] / totals["clicks"]) if totals["clicks"] else None
    conversation_data_complete = bool(snapshots) and all(s.conversations is not None for s in snapshots)
    if not conversation_data_complete:
        totals["conversations"] = None
    else:
        totals["conversations"] = int(totals["conversations"])
    totals["cost_per_conversation_inr"] = (totals["spend_inr"] / totals["conversations"]) if totals["conversations"] else None
    totals["roas"] = (totals["revenue_inr"] / totals["spend_inr"]) if totals["spend_inr"] else None
    recommendation = build_recommendations(ctr=totals["ctr"], cpc_inr=totals["cpc_inr"],
                                           conversations=totals["conversations"],
                                           cost_per_conversation_inr=totals["cost_per_conversation_inr"])
    return {"start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "metrics": dict(totals),
            "conversation_data_complete": conversation_data_complete,
            "recommendations": asdict(recommendation)}
