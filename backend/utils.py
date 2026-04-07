"""
backend/utils.py
Common utilities for data normalization and matching.
"""

import re
import random
import asyncio
from typing import Optional
from loguru import logger

def normalize_team_name(name: str) -> str:
    """
    Standardise team names for robust matching.
    Removes common suffixes, case-flattens, and removes non-word chars.
    """
    if not name:
        return ""
    
    # Lowercase & common acronyms/suffixes
    name = name.lower()
    removals = [
        " f.c.", " fc", " c.f.", " cf", " united", " utd", " town", " city", 
        " rangers", " athletic", " de ", " a.c.", " ac ", " s.c.", " sc ",
        " s.v.", " sv ", " c.d.", " cd ", " f.k.", " fk ", " r.c.", " rc "
    ]
    for r in removals:
        name = name.replace(r, " ")
    
    # Remove all non-alphanumeric except spaces
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    
    # Collapse multiple spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name

def is_same_team(name1: str, name2: str) -> bool:
    """
    Returns True if name1 and name2 likely refer to the same team.
    Uses normalized containment.
    """
    n1 = normalize_team_name(name1)
    n2 = normalize_team_name(name2)
    
    if not n1 or not n2:
        return False
    
    # 1. Exact match
    if n1 == n2:
        return True
    
    # 2. Containment (e.g. 'man united' vs 'manchester united')
    if n1 in n2 or n2 in n1:
        return True
    
    # 3. Simple fuzzy/token matching: if more than half of the tokens match
    tokens1 = set(n1.split())
    tokens2 = set(n2.split())
    if not tokens1 or not tokens2:
        return False
        
    common = tokens1.intersection(tokens2)
    min_len = min(len(tokens1), len(tokens2))
    
    # If 2+ tokens or majority tokens match
    if len(common) >= 2 or (len(common) / min_len) >= 0.5:
        return True
        
    return False

async def jittered_sleep(min_s: float = 1.0, max_s: float = 3.0):
    """Async sleep with random jitter to mimic human behavior."""
    await asyncio.sleep(random.uniform(min_s, max_s))

async def jittered_goto(page, url: str):
    """page.goto with a random pre-sleep to thwart simple rate limits."""
    await jittered_sleep(1.0, 2.5)
    try:
        return await page.goto(url, wait_until="networkidle", timeout=60000)
    except Exception as e:
        logger.warning(f"Jittered goto failed for {url}: {e}")
        raise e
