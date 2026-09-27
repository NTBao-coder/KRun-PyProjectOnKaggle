# Docker-backed launcher for PowerShell 7 or Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
$Repo = $PSScriptRoot
$Image = if ($env:KRUN_IMAGE) { $env:KRUN_IMAGE } else { 'krun:local' }
$CliArgs = @($args)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Install Docker Desktop first.' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop in Linux-container mode and retry docker info.' }
$Files = @(Get-ChildItem "$Repo/krun" -Filter '*.py' -Recurse | Sort-Object FullName | ForEach-Object { $_.FullName })
$Files += @("$Repo/Dockerfile", "$Repo/pyproject.toml", "$Repo/requirements-docker.txt")
$Hashes = ($Files | ForEach-Object { (Get-FileHash $_ -Algorithm SHA256).Hash }) -join ''
$Sha = [System.Security.Cryptography.SHA256]::Create()
$Fingerprint = ([BitConverter]::ToString($Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Hashes)))).Replace('-', '').ToLower()
$Sha.Dispose()
function Build-KRun {
    docker build --label "io.krun.source-hash=$Fingerprint" -t $Image $Repo
    if ($LASTEXITCODE -ne 0) { throw 'Docker build failed.' }
}
if ($CliArgs.Count -gt 0 -and $CliArgs[0] -eq 'build') { Build-KRun; exit 0 }
docker image inspect $Image *> $null
if ($LASTEXITCODE -ne 0) {
    if ($env:KRUN_IMAGE) {
        docker pull $Image
        if ($LASTEXITCODE -ne 0) { throw 'Image pull failed.' }
    } else { Build-KRun }
} elseif (-not $env:KRUN_IMAGE) {
    $Installed = docker image inspect --format '{{ index .Config.Labels "io.krun.source-hash" }}' $Image
    if ($Installed -ne $Fingerprint) { Build-KRun }
}

if ($CliArgs.Count -gt 0 -and $CliArgs[0] -eq 'demo') {
    $Name = if ($CliArgs.Count -gt 1) { $CliArgs[1] } else { 'sales-report' }
    $Extra = if ($CliArgs.Count -gt 2) { @($CliArgs[2..($CliArgs.Count - 1)]) } else { @() }
    switch ($Name) {
        'sales-report' { $DemoRoot = "$Repo/examples/sales_report"; $CliArgs = @('run', 'main.py', '--project', $DemoRoot) + $Extra }
        'module' { $DemoRoot = "$Repo/examples/module_job"; $CliArgs = @('run', '-m', 'report_job', '--project', $DemoRoot) + $Extra }
        'notebook' { $DemoRoot = "$Repo/examples/notebook_job"; $CliArgs = @('run', 'report.ipynb', '--project', $DemoRoot) + $Extra }
        default { throw 'Choose demo sales-report, module, or notebook.' }
    }
    Set-Location $DemoRoot
}
$Original = (Get-Location).Path
$Explicit = $null
$Target = $null
$ValueOptions = @('--module', '-m', '--gpu', '--accelerator', '--owner', '--requirements', '--dependency-project', '--package', '--output', '--input', '--dataset', '--secret', '--cwd', '--timeout', '--cell-timeout', '--path')
for ($Index = 1; $Index -lt $CliArgs.Count; $Index++) {
    $Value = $CliArgs[$Index]
    if ($Value -eq '--') { break }
    if ($Value -eq '--project') { $Index++; if ($Index -ge $CliArgs.Count) { throw '--project needs a directory.' }; $Explicit = $CliArgs[$Index]; continue }
    if ($Value.StartsWith('--project=')) { $Explicit = $Value.Substring(10); continue }
    if ($ValueOptions -contains $Value) { $Index++; continue }
    if ($CliArgs[0] -eq 'run' -and -not $Value.StartsWith('-') -and -not $Target) { $Target = $Value }
}
function Find-Root([string]$Start) {
    foreach ($Markers in @(@('krun.yaml', '.krun/jobs'), @('pyproject.toml', 'requirements.txt', '.git/HEAD', '.git'))) {
        $Current = $Start
        while ($Current) {
            foreach ($Marker in $Markers) {
                $MarkerPath = Join-Path $Current $Marker
                if ($Marker -eq '.git') {
                    if (Test-Path $MarkerPath -PathType Leaf) { return $Current }
                } elseif (Test-Path $MarkerPath) { return $Current }
            }
            $Parent = Split-Path $Current -Parent
            if ($Parent -eq $Current) { break }
            $Current = $Parent
        }
    }
    return $Start
}
if ($Explicit) { $Root = (Resolve-Path $Explicit).Path }
else {
    $Candidate = if ($Target -and (Test-Path $Target -PathType Leaf)) { Split-Path (Resolve-Path $Target).Path -Parent } else { $Original }
    $Root = Find-Root $Candidate
}
function Convert-PathValue([string]$Value) {
    $Absolute = if ([IO.Path]::IsPathRooted($Value)) { [IO.Path]::GetFullPath($Value) }
        elseif (Test-Path (Join-Path $Original $Value)) { [IO.Path]::GetFullPath((Join-Path $Original $Value)) }
        else { [IO.Path]::GetFullPath((Join-Path $Root $Value)) }
    $Prefix = $Root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if ($Absolute -eq $Root) { return '/workspace' }
    if (-not $Absolute.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Path outside project: $Value. Use --project with a common root." }
    return '/workspace/' + $Absolute.Substring($Prefix.Length).Replace('\', '/')
}
$PathOptions = @('--project', '--requirements', '--dependency-project', '--input', '--path')
for ($Index = 1; $Index -lt $CliArgs.Count; $Index++) {
    $Value = $CliArgs[$Index]
    if ($Value -eq '--') { break }
    if ($PathOptions -contains $Value) { $Index++; $CliArgs[$Index] = Convert-PathValue $CliArgs[$Index]; continue }
    if ($Value.Contains('=') -and ($PathOptions -contains $Value.Split('=')[0])) {
        $Pair = $Value.Split(@('='), 2); $CliArgs[$Index] = $Pair[0] + '=' + (Convert-PathValue $Pair[1]); continue
    }
    if ($Target -and $Value -eq $Target) { $CliArgs[$Index] = Convert-PathValue $Value; $Target = $null }
}
New-Item -ItemType Directory -Force -Path "$HOME/.kaggle" | Out-Null
$RunArgs = @('run', '--rm')
if (-not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected) { $RunArgs += '-it' }
elseif ($CliArgs.Count -gt 0 -and $CliArgs[0] -eq 'login') { $RunArgs += '-i' }
$RunArgs += @('--user', '1000:1000', '--tmpfs', '/home/krun:uid=1000,gid=1000,mode=700',
    '--mount', "type=bind,source=$Root,target=/workspace",
    '--mount', "type=bind,source=$HOME/.kaggle,target=/home/krun/.kaggle", '-e', "KRUN_HOST_ROOT=$Root")
foreach ($Name in @('KAGGLE_API_TOKEN', 'KAGGLE_USERNAME', 'KAGGLE_KEY')) {
    if ([Environment]::GetEnvironmentVariable($Name)) { $RunArgs += @('-e', $Name) }
}
& docker @RunArgs $Image @CliArgs
exit $LASTEXITCODE
