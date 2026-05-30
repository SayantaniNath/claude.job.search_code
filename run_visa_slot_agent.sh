#!/bin/bash
# Run the L1 visa slot agent in a loop.
# Cron example (every 30 min):
#   */30 * * * * /path/to/run_visa_slot_agent.sh >> /path/to/visa_slot.log 2>&1

cd "$(dirname "$0")"

if [ -d "venv" ]; then
    source venv/bin/activate
fi

# --once flag makes it a single check (suitable for cron)
python l1_visa_slot_agent.py --once
