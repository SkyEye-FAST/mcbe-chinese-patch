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

    foreach ($line in $langContent) {
        $line = $line.Trim()

        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line.StartsWith("## ")) {
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

function Get-TextsFromZip($zipPath, $extractDir, $targetLanguages) {
    Write-Host "Extracting texts folders from $zipPath..."

    Add-Type -AssemblyName System.IO.Compression.FileSystem

    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
        $textsEntries = $zip.Entries | Where-Object {
            $_.FullName -like "*/resource_packs/*/texts/*" -and
            $_.FullName.EndsWith(".lang")
        } | Sort-Object FullName

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

                $content = $rawContent -split "`r?`n" | ForEach-Object {
                    $line = $_ -replace "^\uFEFF", ""
                    $line
                } | Where-Object { $_ -match '\S' }

                if ($content.Count -gt 0) {
                    $sourcePath = $entry.FullName -replace '^.*(?=resource_packs)', ''

                    if (-not $isFirstEntry[$fileName]) {
                        $langContents[$fileName] += ""
                    }

                    $langContents[$fileName] += "## $sourcePath"
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

$outputDir = Join-Path (Split-Path $PSScriptRoot -Parent) "extracted"
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

            # Output .lang file
            $outputFile = Join-Path $packageOutputDir $langFile
            $content = ($langContents[$langFile] -join "`n") + "`n"
            $utf8NoBom = New-Object System.Text.UTF8Encoding $false
            [System.IO.File]::WriteAllText($outputFile, $content, $utf8NoBom)
            Write-Host "Created $($package.FolderName)\$langFile with $($langContents[$langFile].Count) lines" -ForegroundColor Green

            # Convert to JSON and output .json file
            $jsonData = Convert-LangToJson $langContents[$langFile]
            $jsonFile = $langFile -replace '\.lang$', '.json'
            $jsonOutputFile = Join-Path $packageOutputDir $jsonFile
            $jsonContent = $jsonData | ConvertTo-Json -Depth 100 -Compress:$false
            [System.IO.File]::WriteAllText($jsonOutputFile, $jsonContent, $utf8NoBom)
            Write-Host "Created $($package.FolderName)\$jsonFile with $($jsonData.Count) entries" -ForegroundColor Green
        }
    }

    if (-not $foundAnyLangFiles) {
        Write-Host "No language files found in $($package.Name)" -ForegroundColor Yellow
    }
}

Write-Host "Language file extraction completed!" -ForegroundColor Green
Write-Host "Output directory: $outputDir" -ForegroundColor Cyan
