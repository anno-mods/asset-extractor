@echo off
setlocal enabledelayedexpansion

:: new_playtest_version.bat - Playtest build script for asset-extractor
:: Regenerates the playtest asset browser, item CSV, and Item Inspector build
:: from config.json's playtest cache. Unlike new_version.bat, this does NOT
:: create a version snapshot and does NOT upload to Google Sheets.
::
:: Designed to be double-clicked: always runs from its own directory,
:: regardless of the caller's current directory.

cd /d "%~dp0"

:: Resolve to an absolute path -- pushd/call targets must not be bare relative
:: names, since this and some other environments don't search cwd for them.
for %%D in ("%~dp0..\Anno-117-Item-Inspector") do set ITEM_INSPECTOR_DIR=%%~fD

:: Check if 7-Zip is available
where 7z >nul 2>nul
if errorlevel 1 (
    echo Error: 7-Zip not found in PATH
    echo Please install 7-Zip and add it to your PATH, or edit this script to point to 7z.exe
    echo Hit enter to continue without packing.
    pause
)

echo.
echo ============================================================
echo Asset Extractor - Playtest Build Script
echo ============================================================
echo.

:: Ensure config.json points at a playtest cache before touching anything
for /f "usebackq delims=" %%I in (`uv run python -c "import json; print(json.load(open('config.json'))['cache_path'])"`) do set CACHE_PATH=%%I
echo Config cache_path: %CACHE_PATH%
echo %CACHE_PATH%| findstr /i "playtest" >nul
if errorlevel 1 (
    echo Error: config.json's cache_path does not contain "playtest" ^(found: %CACHE_PATH%^).
    echo Point config.json at your playtest cache/game install before running this script.
    goto :fail
)

:: Get current date in YYYY-MM-DD format
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
set DATE_STAMP=%datetime:~0,4%-%datetime:~4,2%-%datetime:~6,2%
set VERSION=playtest-%DATE_STAMP%

echo.
echo Playtest version tag: %VERSION%
echo.

:: Step 1: Extract RDA files
echo ============================================================
echo Step 1/7: Extracting RDA files from playtest game...
echo ============================================================
echo.
call "%~dp0extract.cmd"
if errorlevel 1 (
    echo Error: Extraction failed
    goto :fail
)

:: Step 2: Generate asset browser (no --version, so no snapshot is created)
echo.
echo ============================================================
echo Step 2/7: Generating asset browser and items CSV...
echo ============================================================
echo.
uv run python main.py
if errorlevel 1 (
    echo Error: Asset browser generation failed
    goto :fail
)

echo Saving items_english_%VERSION%.csv...
uv run python -m assetextractor.conversion.statistics.extract_items_to_csv --version "%VERSION%"
if errorlevel 1 (
    echo Warning: CSV export failed
    echo Continuing...
)

:: Step 3: Zip the asset browser
echo.
echo ============================================================
echo Step 3/7: Creating archive...
echo ============================================================
echo.

set ARCHIVE_NAME=assetbrowser-%VERSION%.7z

for /f "usebackq delims=" %%I in (`uv run python -c "import json; print(json.load(open('config.json'))['assetbrowser_dir'])"`) do set ASSETBROWSER_DIR=%%I
if "%ASSETBROWSER_DIR%"=="" (
    echo Error: Could not read assetbrowser_dir from config.json
    goto :fail
)

echo Creating archive: %ARCHIVE_NAME%
echo Source directory: %ASSETBROWSER_DIR%
echo.

where 7z >nul 2>nul
if errorlevel 1 (
    echo Warning: 7-Zip not found, skipping archive creation.
    goto skip_archive
)
7z a -t7z -m0=lzma2 -mx=7 -md=1024m "%ARCHIVE_NAME%" "%ASSETBROWSER_DIR%\*" -xr^^!.git
if errorlevel 1 (
    echo Error: Archive creation failed
    goto :fail
)
echo.
echo Archive created successfully: %ARCHIVE_NAME%
:skip_archive

:: Step 4: Sync Item Inspector repo -- must be on dev with latest main merged in
:: before we extract icons into its data/ folder.
echo.
echo ============================================================
echo Step 4/7: Syncing Item Inspector repo (dev + latest main)...
echo ============================================================
echo.
if not exist "%ITEM_INSPECTOR_DIR%\.git" (
    echo Error: %ITEM_INSPECTOR_DIR% is not a git repository
    goto :fail
)
pushd "%ITEM_INSPECTOR_DIR%"

for /f "usebackq delims=" %%I in (`git rev-parse --abbrev-ref HEAD`) do set CURRENT_BRANCH=%%I
if not "%CURRENT_BRANCH%"=="dev" (
    echo Current branch is "%CURRENT_BRANCH%", switching to dev...
    git checkout dev
    if errorlevel 1 (
        popd
        echo Error: could not switch Item Inspector to the dev branch. Resolve manually.
        goto :fail
    )
)

echo Fetching origin...
git fetch origin
if errorlevel 1 (
    popd
    echo Error: git fetch failed
    goto :fail
)

echo Merging origin/main into dev ^(conflicts resolved using merge-head, i.e. main^)...
git merge --no-edit -X theirs origin/main
if errorlevel 1 (
    popd
    echo Error: merging origin/main into dev failed. Resolve manually in %ITEM_INSPECTOR_DIR%.
    goto :fail
)
popd

:: Step 5: Populate Item Inspector's data from the playtest cache. This script is
:: self-contained: it always overwrites assets.xml/texts_*.xml and adds any missing
:: icons (no --force, so existing icons are left alone).
echo.
echo ============================================================
echo Step 5/7: Populating Item Inspector data (assets.xml, loca, icons)...
echo ============================================================
echo.
uv run python -m assetextractor.conversion.tools.extract_item_inspector
if errorlevel 1 (
    echo Error: Item Inspector data extraction failed
    goto :fail
)

:: Step 6: Commit the new/updated icons
echo.
echo ============================================================
echo Step 6/7: Committing new assets/icons...
echo ============================================================
echo.
pushd "%ITEM_INSPECTOR_DIR%"
git add data\ui data\base\config
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Playtest %DATE_STAMP%"
    if errorlevel 1 (
        popd
        echo Error: commit failed
        goto :fail
    )
) else (
    echo No new or changed assets/icons to commit.
)
popd

:: Step 7: Build Item Inspector (regenerates its own items_export_with_effects.csv
:: from whatever assets.xml/texts already sit in its data/ folder, see its build.cmd)
echo.
echo ============================================================
echo Step 7/7: Building Item Inspector...
echo ============================================================
echo.
if not exist "%ITEM_INSPECTOR_DIR%\build.cmd" (
    echo Error: build.cmd not found at %ITEM_INSPECTOR_DIR%
    goto :fail
)
pushd "%ITEM_INSPECTOR_DIR%"
call "%ITEM_INSPECTOR_DIR%\build.cmd"
set BUILD_RESULT=%errorlevel%
popd
if not "%BUILD_RESULT%"=="0" (
    echo Error: Item Inspector build failed
    goto :fail
)

echo.
echo ============================================================
echo Playtest build complete!
echo ============================================================
echo.
echo Version tag:     %VERSION%
echo Items CSV:       results\tables\items_english_%VERSION%.csv
echo Archive:         %ARCHIVE_NAME% (if 7-Zip was available)
echo Item Inspector:  %ITEM_INSPECTOR_DIR%\dist\Anno 117 Item Inspector.exe
echo.
echo Not performed (by design): version snapshot, Google Sheets upload.
echo ============================================================
echo.
pause
endlocal
exit /b 0

:fail
echo.
echo Build did not complete successfully -- see the messages above.
pause
endlocal
exit /b 1
