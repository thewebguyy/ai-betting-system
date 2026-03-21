"""
tests/test_risk.py
Validation for Phase 4: Risk Strategy and Bankroll Guardrails.
"""

import pytest
from models.value_model import dynamic_kelly
from automation.workflows import get_consecutive_losses, check_daily_loss_limit
from backend.database import AsyncSessionLocal

def test_dynamic_kelly_constraints():
    # Constraint 1: dynamic_kelly(0.10, 0.85, 3, '1X2', 0.01) returns 0.054 - 0.075
    val1 = dynamic_kelly(0.10, 0.85, 3, '1X2', 0.01)
    assert 0.054 <= val1 <= 0.075, f"Expected 0.054-0.075, got {val1}"
    
    # Constraint 2: dynamic_kelly(0.10, 0.95, 0, 'correct_score', 0.03) returns <= 0.110
    val2 = dynamic_kelly(0.10, 0.95, 0, 'correct_score', 0.03)
    assert val2 <= 0.110, f"Expected <= 0.110, got {val2}"

@pytest.mark.asyncio
async def test_empty_drawdown_fallback():
    # Constraint 3: get_consecutive_losses() returns 0 on empty bets table
    losses = await get_consecutive_losses()
    assert losses == 0
    
    # Constraint 4: check_daily_loss_limit() returns False on empty bets table
    limit_reached = await check_daily_loss_limit()
    assert limit_reached is False
