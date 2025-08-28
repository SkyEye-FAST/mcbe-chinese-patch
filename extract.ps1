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
                Write-Host "Downloading $linkText ..."
                if (Test-Path -Path $linkText) {
                    Write-Host "Already exists, skipping $linkText"
                }
                else {
                    Invoke-WebRequest -Uri $link.href -OutFile $linkText
                }
                return $linkText
            }
        }
    }
    return $null
}

function Get-TextsFromZip($zipPath, $extractDir, $targetLanguages) {
    Write-Host "Extracting texts folders from $zipPath..."

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
        $textsEntries = $zip.Entries | Where-Object {
            $_.FullName -like "*/resource_packs/*/texts/*" -and
            $_.FullName.EndsWith(".lang")
        }

        $langContents = @{}
        foreach ($lang in $targetLanguages) {
            $langContents[$lang] = @()
        }

        $isFirstEntry = @{}
        foreach ($lang in $targetLanguages) {
            $isFirstEntry[$lang] = $true
        }

        foreach ($entry in $textsEntries) {
            $fileName = Split-Path $entry.FullName -Leaf
            if ($fileName -in $targetLanguages) {
                Write-Host "  Extracting: $($entry.FullName)"

                $stream = $entry.Open()
                $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
                $rawContent = $reader.ReadToEnd()
                $reader.Close()
                $stream.Close()

                $content = $rawContent -split "`r?`n" | Where-Object { $_ -match '\S' }

                if ($content.Count -gt 0) {
                    $sourcePath = $entry.FullName -replace '^.*(?=resource_packs)', ''

                    if (-not $isFirstEntry[$fileName]) {
                        $langContents[$fileName] += ""
                    }

                    $langContents[$fileName] += "# $sourcePath"
                    $langContents[$fileName] += $content
                    $isFirstEntry[$fileName] = $false
                }
            }
        }

        return $langContents
    }
    finally {
        if ($zip) { $zip.Dispose() }
    }
}

$packageInfo = @(
    @{ Name = "Microsoft.MinecraftUWP_8wekyb3d8bbwe"; FolderName = "release" },
    @{ Name = "Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"; FolderName = "preview" }
)

$targetLanguages = @("en_US.lang", "zh_CN.lang", "zh_TW.lang")

$outputDir = "$PSScriptRoot\extracted"
if (-not (Test-Path $outputDir)) { New-Item -ItemType Directory -Path $outputDir | Out-Null }

foreach ($package in $packageInfo) {
    Write-Host "Processing package: $($package.Name)" -ForegroundColor Cyan
    $appxFile = Get-AppxFile $package.Name

    if (-not $appxFile) {
        Write-Host "Failed to download appx file for $($package.Name)" -ForegroundColor Yellow
        continue
    }

    $packageOutputDir = Join-Path $outputDir $package.FolderName
    if (-not (Test-Path $packageOutputDir)) {
        New-Item -ItemType Directory -Path $packageOutputDir | Out-Null
    }

    $langContents = Get-TextsFromZip $appxFile $null $targetLanguages

    $foundAnyLangFiles = $false
    foreach ($langFile in $targetLanguages) {
        if ($langContents[$langFile] -and $langContents[$langFile].Count -gt 0) {
            $foundAnyLangFiles = $true
            $outputFile = Join-Path $packageOutputDir $langFile
            $content = ($langContents[$langFile] -join "`n") + "`n"
            [System.IO.File]::WriteAllText($outputFile, $content, [System.Text.Encoding]::UTF8)
            Write-Host "Created $($package.FolderName)\$langFile with $($langContents[$langFile].Count) lines" -ForegroundColor Green
        }
    }

    if (-not $foundAnyLangFiles) {
        Write-Host "No language files found in $($package.Name)" -ForegroundColor Yellow
    }
}

Write-Host "Language file extraction completed!" -ForegroundColor Green
Write-Host "Output directory: $outputDir" -ForegroundColor Cyan
