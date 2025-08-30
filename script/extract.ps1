function Get-AppxFile($Name) {
    $obj = Invoke-WebRequest -Uri "https://store.rg-adguard.net/api/GetFiles" `
        -Method "POST" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{
        type = 'PackageFamilyName'
        url  = $Name
        ring = 'RP'
        lang = 'en-US'
    }

    foreach ($link in $obj.Links) {
        if ($link.outerHTML -match '(?<=<a\b[^>]*>).*?(?=</a>)') {
            $linkText = $Matches[0]
            if ($linkText -match 'x64.*\.appx\b') {
                $appxPath = Join-Path (Split-Path $PSScriptRoot -Parent) $linkText
                Write-Host "Downloading $linkText ..."
                if (Test-Path -Path $appxPath) {
                    Write-Host "Already exists, skipping $linkText"
                }
                else {
                    Invoke-WebRequest -Uri $link.href -OutFile $appxPath
                }
                return $appxPath
            }
        }
    }
    return $null
}

function Convert-LangToJson($langContent) {
    $jsonData = New-Object System.Collections.Specialized.OrderedDictionary

    foreach ($line in $langContent -split "`r?`n") {
        $line = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith("##")) {
            continue
        }

        $equalIndex = $line.IndexOf('=')
        if ($equalIndex -gt 0) {
            $key = $line.Substring(0, $equalIndex).Trim()
            $value = $line.Substring($equalIndex + 1).Trim()

            if (-not $jsonData.Contains($key)) {
                $jsonData[$key] = $value
            }
        }
    }

    return $jsonData
}

function Extract-FilesToStructure($zipPath, $baseOutputDir, $targetLanguages) {
    Write-Host "Extracting files to directory structure from $zipPath..."

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
        $textsEntries = $zip.Entries | Where-Object {
            $_.FullName -like "data/resource_packs/*/texts/*.lang"
        } | Sort-Object FullName

        $foundAny = $false

        foreach ($entry in $textsEntries) {
            $fileName = Split-Path $entry.FullName -Leaf

            if ($fileName -notin $targetLanguages) {
                continue
            }

            Write-Host "  Processing: $($entry.FullName)"

            $stream = $entry.Open()
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
            $rawContent = $reader.ReadToEnd()
            $reader.Close()
            $stream.Close()

            $cleanedContent = $rawContent -replace "^\uFEFF", "" -replace "`r`n", "`n" -replace "`r", "`n"
            $cleanedContent = ($cleanedContent -split "`n" | Where-Object { $_ -match '\S' }) -join "`n"

            if ([string]::IsNullOrWhiteSpace($cleanedContent)) {
                continue
            }

            $relativePath = $entry.FullName -replace '^data/resource_packs/', '' -replace '/texts/', '/'
            $outputFile = Join-Path $baseOutputDir $relativePath
            $outputDir = Split-Path $outputFile -Parent

            if (-not (Test-Path $outputDir)) {
                New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
            }

            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($outputFile, $cleanedContent, $utf8NoBom)
            Write-Host "Created $relativePath"

            $jsonData = Convert-LangToJson $cleanedContent
            $jsonFile = $outputFile -replace '\.lang$', '.json'
            $jsonContent = $jsonData | ConvertTo-Json -Depth 100 -Compress:$false
            [System.IO.File]::WriteAllText($jsonFile, $jsonContent, $utf8NoBom)

            $jsonRelativePath = $relativePath -replace '\.lang$', '.json'
            Write-Host "Created $jsonRelativePath with $($jsonData.Count) entries"

            $foundAny = $true
        }

        return $foundAny
    }
    finally {
        if ($zip) { $zip.Dispose() }
    }
}

function Extract-ReleaseFiles($zipPath, $baseOutputDir, $targetLanguages) {
    Write-Host "Extracting release files from $zipPath..."

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
        $textsEntries = $zip.Entries | Where-Object {
            $_.FullName -like "data/resource_packs/*/texts/*.lang"
        } | Sort-Object FullName

        $foundAny = $false

        foreach ($entry in $textsEntries) {
            $fileName = Split-Path $entry.FullName -Leaf

            if ($fileName -notin $targetLanguages) {
                continue
            }

            $relativePath = $entry.FullName -replace '^data/resource_packs/', '' -replace '/texts/', '/'
            if ($relativePath -like "*beta/*") {
                Write-Host "  Skipping beta path: $relativePath"
                continue
            }

            Write-Host "  Processing: $($entry.FullName)"

            $stream = $entry.Open()
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
            $rawContent = $reader.ReadToEnd()
            $reader.Close()
            $stream.Close()

            $cleanedContent = $rawContent -replace "^\uFEFF", "" -replace "`r`n", "`n" -replace "`r", "`n"
            $cleanedContent = ($cleanedContent -split "`n" | Where-Object { $_ -match '\S' }) -join "`n"

            if ([string]::IsNullOrWhiteSpace($cleanedContent)) {
                continue
            }

            $outputFile = Join-Path $baseOutputDir $relativePath
            $outputDir = Split-Path $outputFile -Parent

            if (-not (Test-Path $outputDir)) {
                New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
            }

            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($outputFile, $cleanedContent, $utf8NoBom)
            Write-Host "Created $relativePath"

            $jsonData = Convert-LangToJson $cleanedContent
            $jsonFile = $outputFile -replace '\.lang$', '.json'
            $jsonContent = $jsonData | ConvertTo-Json -Depth 100 -Compress:$false
            [System.IO.File]::WriteAllText($jsonFile, $jsonContent, $utf8NoBom)

            $jsonRelativePath = $relativePath -replace '\.lang$', '.json'
            Write-Host "Created $jsonRelativePath with $($jsonData.Count) entries"

            $foundAny = $true
        }

        return $foundAny
    }
    finally {
        if ($zip) { $zip.Dispose() }
    }
}

$packageInfo = @(
    @{ Name = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"; FolderName = "release" },
    @{ Name = "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"; FolderName = "development" }
)

$targetLanguages = @("en_US.lang", "zh_CN.lang", "zh_TW.lang")

$outputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "extracted"
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir | Out-Null }

$firstPackage = $true
foreach ($package in $packageInfo) {
    if ($firstPackage) {
        Write-Host "Processing package: $($package.Name)" -ForegroundColor Cyan
        $firstPackage = $false
    } else {
        Write-Host ""
        Write-Host "Processing package: $($package.Name)" -ForegroundColor Cyan
    }

    $appxFile = Get-AppxFile $package.Name

    if (-not $appxFile) {
        Write-Host "Failed to download appx file for $($package.Name)" -ForegroundColor Yellow
        continue
    }

    $packageOutputDir = Join-Path $outputDir $package.FolderName
    if (-not (Test-Path $packageOutputDir)) {
        New-Item -ItemType Directory -Path $packageOutputDir | Out-Null
    }

    $success = $false
    if ($package.Name -eq "Microsoft.MinecraftUWP_8wekyb3d8bbwe") {
        $success = Extract-ReleaseFiles $appxFile $packageOutputDir $targetLanguages
    } else {
        $success = Extract-FilesToStructure $appxFile $packageOutputDir $targetLanguages
    }

    if (-not $success) {
        Write-Host "Failed to extract language files from $appxFile" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Language file extraction completed!" -ForegroundColor Green
Write-Host "Output directory: $outputDir" -ForegroundColor Cyan
