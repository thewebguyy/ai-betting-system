@echo off
echo 🛠️ Setting up AI Betting Local Production Environment...

:: 1. Create Directories
if not exist "logs" mkdir logs
if not exist "data" mkdir data

:: 2. Install Dependencies
echo 📦 Installing core requirements...
python -m pip install -r requirements.txt

:: 3. Run Supervisor
echo 🚀 Launching Local Supervisor...
python run_local.py

pause
