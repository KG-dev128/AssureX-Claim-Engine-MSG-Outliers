$projectDirectory = $PSScriptRoot
$runtimePython = Join-Path $projectDirectory '.runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw 'Create .runtime with Python 3.12 and install requirements.txt first. See README.md.'
}
$env:ASSUREX_OCR_ENGINE = 'easyocr'
& $runtimePython (Join-Path $projectDirectory 'app.py')
