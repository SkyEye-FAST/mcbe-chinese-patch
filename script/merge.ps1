$ErrorActionPreference = 'Stop'

$mergeOrder = @(
    'vanilla',
    'experimental_*',
    'oreui',
    'persona',
    'editor',
    'chemistry',
    'education',
    'education_demo'
)

$targets = @(
    @{ Name = 'release'; Path = 'extracted/release' },
    @{ Name = 'beta'; Path = 'extracted/development' },
    @{ Name = 'preview'; Path = 'extracted/development' }
)

$langFiles = @('en_US.json', 'zh_CN.json', 'zh_TW.json')

function Merge-LangFiles {
    param(
        [string[]]$fileList
    )
    $merged = @{}
    foreach ($file in $fileList) {
        if (Test-Path $file) {
            $content = [System.IO.File]::ReadAllText($file, [System.Text.Encoding]::UTF8)
            $data = $content | ConvertFrom-Json
            $data.PSObject.Properties | ForEach-Object {
                if (-not $merged.ContainsKey($_.Name)) {
                    $merged[$_.Name] = $_.Value
                }
            }
        }
    }
    $sortedKeys = $merged.Keys | Sort-Object
    $sortedMerged = [ordered]@{}
    foreach ($key in $sortedKeys) {
        $sortedMerged[$key] = $merged[$key]
    }
    return $sortedMerged
}

function Get-OrderedSubDirs {
    param(
        [string]$baseDir,
        [string[]]$excludeDirs = @()
    )
    $dirs = Get-ChildItem -Path $baseDir -Directory | ForEach-Object { $_.Name }
    $dirs = $dirs | Where-Object { $excludeDirs -notcontains $_ }
    $ordered = @()
    foreach ($pattern in $mergeOrder) {
        if ($pattern -like '*_*') {
            $matched = $dirs | Where-Object { $_ -like $pattern }
            $ordered += $matched
        }
        else {
            if ($dirs -contains $pattern) {
                $ordered += $pattern
            }
        }
    }
    $others = $dirs | Where-Object { $ordered -notcontains $_ }
    $ordered += $others
    return $ordered
}

foreach ($target in $targets) {
    $baseDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
    $srcDir = Join-Path $baseDir $target.Path
    if (-not (Test-Path $srcDir)) { continue }

    $outDir = Join-Path $baseDir "merged/$($target.Name)"
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

    if ($target.Name -eq 'beta') {
        $orderedSubDirs = Get-OrderedSubDirs $srcDir @('previewapp')
        $betaDir = Join-Path $srcDir 'beta'
        if (Test-Path $betaDir) {
            $betaSubDirs = Get-OrderedSubDirs $betaDir
            $orderedSubDirs += $betaSubDirs | ForEach-Object { "beta/$_" }
        }
    }
    elseif ($target.Name -eq 'preview') {
        $orderedSubDirs = Get-OrderedSubDirs $srcDir @('beta')
        $previewDir = Join-Path $srcDir 'previewapp'
        if (Test-Path $previewDir) {
            $previewSubDirs = Get-OrderedSubDirs $previewDir
            $orderedSubDirs += $previewSubDirs | ForEach-Object { "previewapp/$_" }
        }
    }
    else {
        $orderedSubDirs = Get-OrderedSubDirs $srcDir
    }

    foreach ($lang in $langFiles) {
        $fileList = @()
        foreach ($sub in $orderedSubDirs) {
            $subDir = Join-Path $srcDir $sub
            $f = Join-Path $subDir $lang
            if (Test-Path $f) { $fileList += $f }
        }
        if ($fileList.Count -eq 0) { continue }
        $merged = Merge-LangFiles $fileList
        $outFile = Join-Path $outDir $lang
        $jsonContent = $merged | ConvertTo-Json -Depth 100 -Compress:$false
        [System.IO.File]::WriteAllText($outFile, $jsonContent, [System.Text.Encoding]::UTF8)
        Write-Host "Merged $($fileList.Count) files to $outFile"
        Write-Host "  Total keys: $($merged.Count)"
        Write-Host "  Files merged:"
        foreach ($file in $fileList) {
            Write-Host "    $file"
        }
    }
}

$baseDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$mergeDir = Join-Path $baseDir "merged"
Write-Host "All language files merged! Output: $mergeDir"
