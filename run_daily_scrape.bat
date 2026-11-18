@echo off
:: Micraft Daily Lead Harvest - runs at 6:00 AM via Windows Task Scheduler
:: Logs to logs\daily_scrape.log — rotate monthly if it grows large

cd /d E:\Development\MicraftLeadGeneration

echo ============================================================ >> logs\daily_scrape.log
echo DAILY SCRAPE STARTED: %DATE% %TIME% >> logs\daily_scrape.log
echo ============================================================ >> logs\daily_scrape.log

call venv\Scripts\activate.bat

:: MES campaign — IndiaMart + TradeIndia + Google Maps
echo [MES] Starting... >> logs\daily_scrape.log
python scripts\run_scraper.py --product mes --source indiamart --target 20 --yes >> logs\daily_scrape.log 2>&1
python scripts\run_scraper.py --product mes --source tradeindia --target 15 --yes >> logs\daily_scrape.log 2>&1
python scripts\run_scraper.py --product mes --source google_maps --target 10 --yes >> logs\daily_scrape.log 2>&1

:: Calibration MS — NABL (until exhausted, then falls back to 0 new)
echo [CALIBRATION] Starting... >> logs\daily_scrape.log
python scripts\run_scraper.py --product calibration --source nabl --target 20 --yes >> logs\daily_scrape.log 2>&1

:: TMS campaign — IBA transporters
echo [TMS] Starting... >> logs\daily_scrape.log
python scripts\run_scraper.py --product tms --source iba_transporters --target 15 --yes >> logs\daily_scrape.log 2>&1

echo ============================================================ >> logs\daily_scrape.log
echo DAILY SCRAPE COMPLETED: %DATE% %TIME% >> logs\daily_scrape.log
echo ============================================================ >> logs\daily_scrape.log
echo. >> logs\daily_scrape.log
