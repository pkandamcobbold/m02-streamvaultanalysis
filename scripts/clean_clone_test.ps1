<#
.SYNOPSIS
    Proves the repository installs and runs from a clean clone.

.DESCRIPTION
    The test suite cannot prove this. Pytest is configured to find the code in
    pipeline/ whether or not `pip install` succeeded, so a green suite says
    nothing about whether someone who has just cloned the repo can run it.
    Only an actual clone can, and until this script existed that check was a
    paragraph in the README asking somebody to remember to do it by hand.

    It is deliberately a script and not a test: it clones, builds a fresh
    virtual environment and reaches the network, so it belongs beside the
    repository rather than inside `python -m pytest`.

    Clones into a temporary directory, installs from requirements.txt alone,
    checks the package imports with no PYTHONPATH, runs the suite, and -  if
    given a token -  runs the pipeline end to end and checks the artefacts it
    must leave behind. Exits non-zero on the first failure that matters.

.PARAMETER Source
    What to clone. Defaults to the GitHub remote, which is what a marker would
    use. Pass a local path to test the committed state of this working copy.

.PARAMETER EnvFile
    Optional path to a .env holding TMDB_BEARER_TOKEN. Without it the script
    stops after the suite and reports the live run as not attempted -  because
    a credential is the one thing a clone legitimately cannot carry.

.PARAMETER KeepClone
    Leave the clone in place for inspection. Off by default: with -EnvFile the
    clone contains a copy of your token.

.EXAMPLE
    .\scripts\clean_clone_test.ps1 -EnvFile .env
#>
param(
    [string]$Source = "https://github.com/pkandamcobbold/m02-streamvaultanalysis.git",
    [string]$EnvFile = "",
    [switch]$KeepClone
)

$ErrorActionPreference = "Stop"
$script:Failures = @()
$Clone = Join-Path $env:TEMP "streamvault-clean-clone-test"

function Invoke-Native {
    <#
        Runs a native command and returns its exit code, with both streams
        captured rather than piped.

        PowerShell turns a native command's stderr into ErrorRecords, so under
        $ErrorActionPreference = "Stop" any tool that writes an advisory note
        there - pip's upgrade notice, for one - throws and fails a step that
        actually succeeded. That is a false FAIL, which is worse than a missing
        check: it trains the reader to ignore the script.
    #>
    param([string]$FilePath, [string[]]$Arguments, [switch]$Show)
    $out = Join-Path $env:TEMP "cct-stdout.txt"
    $err = Join-Path $env:TEMP "cct-stderr.txt"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments `
        -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $script:LastNativeOutput = (Get-Content $out -Raw) + (Get-Content $err -Raw)
    if ($Show) { Write-Host $script:LastNativeOutput }
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    return $proc.ExitCode
}

function Step {
    param([string]$Name, [scriptblock]$Body)
    Write-Host ""
    Write-Host "== $Name" -ForegroundColor Cyan
    try {
        & $Body
        Write-Host "   PASS" -ForegroundColor Green
    } catch {
        Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
        $script:Failures += $Name
    }
}

Write-Host "Clean-clone test" -ForegroundColor White
Write-Host "source: $Source"
Write-Host "clone : $Clone"

# Resolved against the caller's directory, before Set-Location moves us into
# the clone. ".env" meant the clone's .env, which by definition does not exist.
$TokenFile = ""
if ($EnvFile) {
    $TokenFile = (Resolve-Path -LiteralPath $EnvFile).Path
}
$Origin = (Get-Location).Path

Step "Clone into an empty directory" {
    if (Test-Path $Clone) { Remove-Item -Recurse -Force $Clone }
    git clone --quiet $Source $Clone
    if (-not (Test-Path (Join-Path $Clone "run_pipeline.py"))) {
        throw "clone does not contain run_pipeline.py"
    }
}

Set-Location $Clone

Step "The clone carries no secret and no cache" {
    # If either of these is present the test is not clean: it would be reading
    # data the clone brought with it rather than fetching for itself.
    if (Test-Path ".env") { throw ".env is present in the clone -  it must be gitignored" }
    $cached = @(Get-ChildItem "data/raw" -Filter *.json -ErrorAction SilentlyContinue)
    if ($cached.Count -gt 0) { throw "$($cached.Count) cached responses in the clone" }
    if (-not (Test-Path "data/input/id_list.csv")) { throw "the given input list is missing" }
}

Step "Install from requirements.txt alone" {
    if ((Invoke-Native "python" @("-m", "venv", ".venv")) -ne 0) {
        throw "venv creation failed"
    }
    $code = Invoke-Native ".\.venv\Scripts\python.exe" `
        @("-m", "pip", "install", "--quiet", "-r", "requirements.txt")
    if ($code -ne 0) {
        throw "pip install failed with exit $code, the check that caught S-05`n$script:LastNativeOutput"
    }
}

Step "Import with no PYTHONPATH and no sys.path edit" {
    # The statement is quoted inside the argument, because Start-Process splits
    # each -ArgumentList element on whitespace: an unquoted "import pipeline"
    # reaches python as two arguments and fails with a SyntaxError on "-c import".
    $code = Invoke-Native ".\.venv\Scripts\python.exe" @("-c", '"import pipeline"')
    if ($code -ne 0) {
        throw "import pipeline failed, so the editable install did not take`n$script:LastNativeOutput"
    }
}

Step "The suite passes in the clone" {
    $code = Invoke-Native ".\.venv\Scripts\python.exe" @("-m", "pytest", "-q") -Show
    if ($code -ne 0) { throw "tests failed in the clone" }
}

Step "Without a token it stops with an instruction, not a traceback" {
    # No 2>&1 here. PowerShell wraps a native command's stderr lines in
    # ErrorRecords, and with $ErrorActionPreference = "Stop" the first log line
    # the pipeline writes would throw - which is exactly what it did. Capture
    # both streams to files instead and read them back.
    $out = Join-Path $env:TEMP "cct-out.txt"
    $err = Join-Path $env:TEMP "cct-err.txt"
    $proc = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
        -ArgumentList "run_pipeline.py" -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $output = (Get-Content $out -Raw) + (Get-Content $err -Raw)
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    if ($proc.ExitCode -ne 1) { throw "expected exit 1 with no token, got $($proc.ExitCode)" }
    if ($output -notmatch "TMDB_BEARER_TOKEN") {
        throw "the no-token message does not say which variable to set"
    }
    if ($output -match "Traceback") { throw "a traceback reached the user" }
}

if (-not $EnvFile) {
    Write-Host ""
    Write-Host "== Live run: NOT ATTEMPTED (no -EnvFile given)" -ForegroundColor Yellow
    Write-Host "   Re-run with -EnvFile .env to test the pipeline end to end."
} else {
    Step "Supply the credential a clone cannot carry" {
        Copy-Item -LiteralPath $TokenFile -Destination ".env"
    }

    # The clone ships committed artefacts - the ledger, the KPI tables and the
    # reports are evidence and are version-controlled. So "the file exists" is
    # not evidence that this run produced it: the first version of this script
    # reported both artefact checks as PASS on a run where the pipeline had
    # failed to start. Everything below is checked against this timestamp.
    $RunStarted = Get-Date

    Step "Run the pipeline end to end" {
        $code = Invoke-Native ".\.venv\Scripts\python.exe" @("run_pipeline.py")
        if ($code -eq 2) { throw "the release gate blocked publication (exit 2)" }
        if ($code -ne 0) { throw "pipeline exited $code`n$script:LastNativeOutput" }
    }

    Step "Both time windows were answered" {
        foreach ($file in @("data/processed/kpi_all_years.csv",
                            "data/processed/kpi_modern.csv",
                            "data/processed/kpi_flip_check.csv")) {
            if (-not (Test-Path $file)) { throw "$file is missing" }
            if ((Get-Item $file).LastWriteTime -lt $RunStarted) {
                throw "$file was not rewritten by this run - it is the committed copy"
            }
        }
    }

    Step "Every deliverable was written" {
        # memo, improvement and spotcheck are generated every run. The
        # diagnosis and the decision notes are written by hand, so they are
        # checked for presence only.
        foreach ($file in @("reports/memo.md", "reports/improvement.md",
                            "reports/spotcheck.md")) {
            if (-not (Test-Path $file)) { throw "$file is missing" }
            if ((Get-Item $file).LastWriteTime -lt $RunStarted) {
                throw "$file was not regenerated by this run"
            }
        }
        foreach ($file in @("reports/data_diagnosis.md",
                            "reports/decision_notes.md")) {
            if (-not (Test-Path $file)) { throw "$file is missing" }
        }
    }

    Step "The memo dates itself from the data" {
        $memo = Get-Content "reports/memo.md" -Raw
        if ($memo -notmatch "data as it stood on \d{4}-\d{2}-\d{2}") {
            throw "the memo carries no as-of date"
        }
        if ($memo -match "were not re-checked against the live source") {
            throw "the memo says the spot-check did not run"
        }
    }
}

Set-Location $Origin          # leave the caller where they started
if (-not $KeepClone) {
    Remove-Item -Recurse -Force $Clone -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "clone deleted (it held a copy of your token)" -ForegroundColor DarkGray
} else {
    Write-Host ""
    Write-Host "clone kept at $Clone -  it may hold your token" -ForegroundColor Yellow
}

Write-Host ""
if ($script:Failures.Count -eq 0) {
    Write-Host "CLEAN-CLONE TEST PASSED" -ForegroundColor Green
    exit 0
}
Write-Host "CLEAN-CLONE TEST FAILED: $($script:Failures.Count) step(s)" -ForegroundColor Red
$script:Failures | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
exit 1
