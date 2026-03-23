"""
scripts/migrate.py
Robust Alembic migration script for production and development.
Handles existing legacy databases that were created with Base.metadata.create_all()
by stamping the schema before upgrading.
"""

import sys
import os
import subprocess
from pathlib import Path
from loguru import logger

# Add root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

def run_migrations():
    """Run Alembic migrations with fallback logic for existing un-stamped databases."""
    logger.info("Attempting database migration via Alembic...")
    
    # Run the upgrade
    # We use subprocess to isolate the alembic environment execution context
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"], 
        capture_output=True, 
        text=True
    )
    
    if result.returncode == 0:
        logger.success("✅ Database up-to-date with Alembic schema.")
    else:
        # Check if error implies tables already exist (e.g., 'already exists' in sqlite/pg)
        if "already exists" in result.stderr.lower() or "OperationalError" in result.stderr:
            logger.warning("Legacy database schema detected without Alembic tracking.")
            logger.info("Stamping database with 'head' to transition to Alembic control...")
            
            stamp_result = subprocess.run(
                [sys.executable, "-m", "alembic", "stamp", "head"], 
                capture_output=True, 
                text=True
            )
            
            if stamp_result.returncode == 0:
                logger.success("✅ Database stamped successfully. Alembic now controls schema.")
            else:
                logger.error(f"Failed to stamp database: {stamp_result.stderr}")
                sys.exit(1)
        else:
            logger.error(f"Migration failed with unknown error:\n{result.stderr}")
            sys.exit(1)

if __name__ == "__main__":
    run_migrations()
