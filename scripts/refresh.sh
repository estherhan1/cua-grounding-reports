#!/bin/bash
# Re-snapshot the live run and rebuild the dashboard.
set -e
cd /local3/yuhan/tmp/a3dash
/local3/yuhan/envs/a3/bin/python collect.py
/local3/yuhan/envs/vwa/bin/python collect_env.py
/local3/yuhan/envs/a3/bin/python collect_episodes.py
/local3/yuhan/envs/a3/bin/python render.py
