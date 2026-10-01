from app.services.budget_diagnosis import diagnose_budget
from test_live_integration import local, graph, make_ready
import json

PLAN = {'weekly_budget_inr':150,'start_date':'2026-10-01','end_date':'2026-10-02'}

def test_minimum_is_total_not_daily_and_does_not_change_plan():
    before = dict(PLAN)
    d = diagnose_budget(PLAN,'code 100, subcode 1885272. Your ad set budget must be more than ₹157.79 or your ads may not deliver.')
    assert PLAN == before
    assert d['whole_rupee_total_above_minimum'] == 158
    assert d['max_full_days_at_158_per_day'] == 6
    assert d['approved_total'] == 150
    assert 'cannot satisfy both' not in d['message']

def test_infeasible_total_shows_requested_message_and_keeps_ceiling():
    d = diagnose_budget(PLAN,'1885272: budget must be more than ₹1,050.00')
    assert d['whole_rupee_total_above_minimum'] == 1051
    assert d['message'] == "Meta requires a higher budget for this campaign configuration. The current schedule cannot satisfy both Meta's minimum and your ₹1,050 campaign limit."
    assert 'unavailable' in d['options'][1]

def test_missing_minimum_does_not_guess():
    assert diagnose_budget(PLAN,'100: permission denied') is None
    assert 'reported_minimum_total_exclusive' not in diagnose_budget(PLAN,'1885272')

def test_explicit_audience_setting_preserves_approved_targeting(local, graph):
    client,settings = local
    identifier, plan,_ = make_ready(client,amount=0,total=150)
    settings.meta_paused_preparation_enabled = True
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    targeting = json.loads(graph.posts[1][1]['targeting'])
    assert targeting['targeting_automation'] == {'advantage_audience':0}
    assert targeting['geo_locations'] == {'regions':[{'key':'99'}]}
