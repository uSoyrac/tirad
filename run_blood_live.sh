#!/bin/bash
echo "Starting BLOOD Live Scanner..."
while true; do
    python3 bot_blood.py
    echo "Sleeping for 5 minutes..."
    sleep 300
done
