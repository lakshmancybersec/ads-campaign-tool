"""Explain a Meta minimum; never edit or approve campaign budgets."""
import re
from decimal import Decimal, ROUND_FLOOR

def diagnose_budget(plan, error):
    if '1885272' not in (error or ''):
        return None
    match = re.search(r'more than\s*₹\s*([\d,]+(?:\.\d+)?)', error)
    if not match:
        return {'message':'Meta rejected the budget. Review the exact error before changing dates or budget.', 'options':[]}
    minimum = Decimal(match[1].replace(',', ''))
    required = int(minimum.to_integral_value(rounding=ROUND_FLOOR)) + 1
    limit = 1050
    impossible = required > limit
    return {
        'reported_minimum_total_exclusive': str(minimum),
        'whole_rupee_total_above_minimum': required,
        'approved_total':plan['weekly_budget_inr'],
        'application_total_ceiling':limit,
        'start_date':plan['start_date'], 'end_date':plan['end_date'],
        'max_full_days_at_158_per_day':limit // 158,
        'message': ('Meta requires a higher budget for this campaign configuration. The current schedule cannot satisfy both Meta\'s minimum and your ₹1,050 campaign limit.' if impossible else
                    'Meta rejected the approved total for this schedule. Its reported minimum is a campaign total, not a daily requirement. A date or budget revision requires your approval.'),
        'options': [
            'A. Shorten campaign schedule — keep the approved budget; validate the proposed dates first.',
            'B. Increase campaign total limit — owner approval required; maximum ₹1,050 remains unchanged.' if not impossible else
            'B. Increase campaign total limit — unavailable under the unchanged ₹1,050 ceiling.',
            'C. Change supported campaign configuration — requires validation and fresh approval.',
            'D. Cancel campaign — requires your explicit instruction.',
        ],
        'note':'The minimum can change with the actual start time. Day-count arithmetic is not proof of Meta acceptance. No option is selected or applied automatically.'
    }
