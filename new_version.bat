@echo off
setlocal enabledelayedexpansion

:: new_version.bat - Automated release build script for asset-extractor
:: This script performs a complete release build with versioning and archiving

:: Check if 7-Zip is available
where 7z >nul 2>nul
if errorlevel 1 (
    echo Error: 7-Zip not found in PATH
    echo Please install 7-Zip and add it to your PATH, or edit this script to point to 7z.exe
    echo Hit enter to continue without packing.
    pause
)

:: Check if Google Sheets credentials file exists
if not exist "gsheet_credentials.json" (
    echo Warning: gsheet_credentials.json not found
    echo Google Sheets export will be skipped.
    echo Hit enter to continue without exporting.
    pause
)


echo.
echo ============================================================
echo Asset Extractor - New Version Release Script
echo ============================================================
echo.

:: Ask for version number
set /p VERSION="Enter version number (e.g., 1.0.0): "
if "%VERSION%"=="" (
    echo Error: Version number is required
    exit /b 1
)

echo.
echo Creating release for version: %VERSION%
echo.

:: Step 1: Extract RDA files
echo ============================================================
echo Step 1/5: Extracting RDA files from game...
echo ============================================================
echo.
call extract.cmd
if errorlevel 1 (
    echo Error: Extraction failed
    exit /b 1
)

:: Step 2: Run main.py with version parameter
echo.
echo ============================================================
echo Step 2/5: Generating asset browser and creating snapshot...
echo ============================================================
echo.
uv run python main.py --version "%VERSION%"
if errorlevel 1 (
    echo Error: Asset browser generation or snapshot creation failed
    exit /b 1
)

echo Saving items_english_%VERSION%.csv...
uv run python -m assetextractor.conversion.statistics.extract_items_to_csv --version "%VERSION%"
if errorlevel 1 (
    echo Warning: CSV export failed
    echo Continuing...
)

pause

:skip_main
:: Step 3: Zip the results
echo.
echo ============================================================
echo Step 3/5: Creating archive...
echo ============================================================
echo.

:: Get current date in YYYY-MM-DD format
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set DATE_STAMP=%%I

set ARCHIVE_NAME=assetbrowser-%DATE_STAMP%.7z

for /f "usebackq delims=" %%I in (`uv run python -c "import json; print(json.load(open('config.json'))['assetbrowser_dir'])"`) do set ASSETBROWSER_DIR=%%I
if "%ASSETBROWSER_DIR%"=="" (
    echo Error: Could not read assetbrowser_dir from config.json
    exit /b 1
)

echo Creating archive: %ARCHIVE_NAME%
echo Source directory: %ASSETBROWSER_DIR%
echo.

:: Create archive with LZMA2, 1GB dictionary, compression level 7 (maximum)
where 7z >nul 2>nul
if errorlevel 1 (
    echo Warning: 7-Zip not found, skipping archive creation.
    goto skip_archive
)
7z a -t7z -m0=lzma2 -mx=7 -md=1024m "%ARCHIVE_NAME%" "%ASSETBROWSER_DIR%\*" -xr^^!.git
if errorlevel 1 (
    echo Error: Archive creation failed
    exit /b 1
)
echo.
echo Archive created successfully: %ARCHIVE_NAME%
:skip_archive

:: Step 4: Export items to CSV and Google Sheets
echo.
echo ============================================================
echo Step 4/5: Exporting items...
echo ============================================================
echo.

if not exist "gsheet_credentials.json" (
    echo Skipping Google Sheets export: gsheet_credentials.json not found.
    goto skip_gsheet
)
echo Uploading to Google Sheets...
uv run python -m assetextractor.conversion.statistics.extract_items_to_gsheet
if errorlevel 1 (
    echo Warning: Google Sheets export failed
    echo Continuing...
)
:skip_gsheet

:: Step 5: Summary
echo.
echo ============================================================
echo Step 5/5: Release build complete!
echo ============================================================
echo.
echo Version: %VERSION%
echo Archive: %ARCHIVE_NAME% (if 7-Zip was available)
echo Output directory: %ASSETBROWSER_DIR%
echo.
echo Next steps:
echo   1. Upload %ARCHIVE_NAME% to your distribution platform (if created)
echo   2. Verify Google Sheets export (if configured)
echo   3. Update release notes
echo.
echo ============================================================

endlocal
