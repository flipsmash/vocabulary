#!/usr/bin/env python3
"""
Daily Vocabulary Harvest Scheduler
Simple script for automated daily vocabulary harvesting
"""

import asyncio
import sys
import logging
from datetime import datetime
from vocabulary_orchestrator import VocabularyOrchestrator, HarvestGoals

# Configure logging for scheduled runs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('C:/Users/Brian/vocabulary/logs/daily_harvest.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

async def run_daily_harvest():
    """Run the daily vocabulary harvest"""
    logger.info("Starting automated daily vocabulary harvest")
    
    try:
        # Configure harvest goals
        goals = HarvestGoals(
            daily_candidates_target=200,    # Target 200 new candidates per day
            max_runtime_minutes=30,         # Max 30 minutes runtime
            min_candidates_per_source=15,   # At least 15 candidates per source
            source_priorities={
                'gutenberg': 1,      # Classical literature (highest priority)
                'wiktionary': 2,     # Archaic terms
                'arxiv': 3,          # Academic papers
                'wikipedia': 4,      # General knowledge
                'universal_extractor': 5,  # Text extraction
                'pubmed': 6,         # Medical terms
                'news_api': 7        # Contemporary usage (lowest priority)
            }
        )
        
        orchestrator = VocabularyOrchestrator(goals)
        
        # Run harvest (will automatically check timing and skip if needed)
        result = await orchestrator.run_daily_harvest()
        
        # Log results
        logger.info(f"Daily harvest completed: {result}")
        
        if result.get('status') == 'skipped':
            logger.info(f"Harvest skipped: {result.get('reason', 'Unknown reason')}")
            return True
        
        # Report success metrics
        total_candidates = result.get('total_candidates', 0)
        target_met = result.get('target_met', False)
        runtime = result.get('runtime_minutes', 0)
        
        logger.info(f"SUCCESS - Found {total_candidates:,} candidates in {runtime:.1f} minutes")
        logger.info(f"Target met: {target_met}")
        
        if result.get('failed_sources'):
            logger.warning(f"Some sources failed: {result['failed_sources']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Daily harvest failed: {e}", exc_info=True)
        return False

def create_windows_task_scheduler():
    """Instructions for setting up Windows Task Scheduler"""
    instructions = """
    Windows Task Scheduler Setup:
    ============================
    
    1. Open Task Scheduler (taskschd.msc)
    
    2. Create Basic Task:
       - Name: "Daily Vocabulary Harvest"  
       - Trigger: Daily at 2:00 AM
       - Action: Start a program
       
    3. Program Settings:
       - Program: C:\\Python313\\python.exe
       - Arguments: C:\\Users\\Brian\\vocabulary\\daily_harvest_scheduler.py
       - Start in: C:\\Users\\Brian\\vocabulary
    
    4. Advanced Settings:
       - Run whether user is logged on or not: YES
       - Run with highest privileges: YES
       - Configure for Windows 10/11
    
    5. Test the task:
       - Right-click task -> "Run"
       - Check logs at: C:/Users/Brian/vocabulary/logs/daily_harvest.log
    """
    return instructions

def create_cron_setup():
    """Instructions for setting up cron (Linux/Mac)"""
    instructions = """
    Cron Setup (Linux/Mac):
    ======================
    
    1. Edit crontab:
       crontab -e
    
    2. Add daily harvest job (runs at 2:00 AM daily):
       0 2 * * * cd /path/to/vocabulary && python3 daily_harvest_scheduler.py
    
    3. Alternative times:
       0 8 * * *   # 8:00 AM daily
       0 14 * * *  # 2:00 PM daily
       0 2 * * 1   # 2:00 AM every Monday
       
    4. Check logs:
       tail -f /path/to/vocabulary/logs/daily_harvest.log
    """
    return instructions

async def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        if sys.argv[1] == '--setup-windows':
            print(create_windows_task_scheduler())
            return
        elif sys.argv[1] == '--setup-cron':
            print(create_cron_setup())
            return
        elif sys.argv[1] == '--test':
            print("Running test harvest...")
            success = await run_daily_harvest()
            sys.exit(0 if success else 1)
    
    # Run the actual daily harvest
    success = await run_daily_harvest()
    
    # Exit with appropriate code for schedulers
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    # Ensure logs directory exists
    import os
    log_dir = "C:/Users/Brian/vocabulary/logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    asyncio.run(main())