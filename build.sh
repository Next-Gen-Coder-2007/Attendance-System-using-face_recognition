#!/usr/bin/env bash

# Update packages
apt-get update

# Install dependencies for dlib
apt-get install -y build-essential cmake libopenblas-dev liblapack-dev libx11-dev libgtk-3-dev python3-dev

# Install Python dependencies
pip install -r requirements.txt
