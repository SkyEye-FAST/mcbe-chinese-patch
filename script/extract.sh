#!/bin/bash

get_appx_file() {
    local name="$1"

    echo "Getting download links for $name..." >&2

    local response=$(curl -s -X POST "https://store.rg-adguard.net/api/GetFiles" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "type=PackageFamilyName&url=${name}&ring=RP&lang=en-US")

    local download_url=$(echo "$response" | grep -oP 'href="\K[^"]*(?="[^>]*>[^<]*x64[^<]*\.appx)' | head -1)
    local filename=$(echo "$response" | grep -oP '>[^<]*x64[^<]*\.appx<' | sed 's/[><]//g' | head -1)

    if [[ -z "$download_url" || -z "$filename" ]]; then
        echo "No x64 appx file found for $name" >&2
        return 1
    fi

    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local appx_path="$script_dir/../$filename"

    echo "Downloading $filename ..." >&2

    if [[ -f "$appx_path" ]]; then
        echo "Already exists, skipping $filename" >&2
    else
        if ! curl -L -o "$appx_path" "$download_url"; then
            echo "Failed to download $filename" >&2
            return 1
        fi
    fi

    echo "$appx_path"
    return 0
}

get_texts_from_zip() {
    local zip_path="$1"
    local output_dir="$2"
    local target_languages=("${@:3}")

    echo "Extracting texts folders from $zip_path..." >&2

    local temp_dir=$(mktemp -d)

    if ! unzip -q "$zip_path" "data/resource_packs/*/texts/*.lang" -d "$temp_dir" 2>/dev/null; then
        echo "Warning: No language files found or extraction failed for $zip_path" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    declare -A lang_contents
    declare -A is_first_entry

    for lang in "${target_languages[@]}"; do
        lang_contents["$lang"]=""
        is_first_entry["$lang"]=true
    done

    local sorted_files=()
    while IFS= read -r -d '' file; do
        sorted_files+=("$file")
    done < <(find "$temp_dir" -name "*.lang" -type f -print0 | sort -z)

    for file in "${sorted_files[@]}"; do
        local filename=$(basename "$file")

        local is_target=false
        for lang in "${target_languages[@]}"; do
            if [[ "$filename" == "$lang" ]]; then
                is_target=true
                break
            fi
        done

        if [[ "$is_target" == "true" ]]; then
            echo "  Extracting: $file" >&2

            local source_path=$(echo "$file" | sed "s|^$temp_dir/||" | sed 's|^data/||')

            if [[ -s "$file" ]]; then
                local valid_lines=()
                while IFS= read -r line || [[ -n "$line" ]]; do
                    line="${line#﻿}"
                    line="${line%$'\r'}"
                    if [[ "$line" =~ [^[:space:]] ]]; then
                        valid_lines+=("$line")
                    fi
                done < "$file"

                if [[ ${#valid_lines[@]} -gt 0 ]]; then
                    if [[ "${is_first_entry[$filename]}" != "true" ]]; then
                        lang_contents["$filename"]+=$'\n'
                    fi

                    lang_contents["$filename"]+="# $source_path"$'\n'
                    for line in "${valid_lines[@]}"; do
                        lang_contents["$filename"]+="$line"$'\n'
                    done
                    is_first_entry["$filename"]=false
                fi
            fi
        fi
    done

    rm -rf "$temp_dir"

    local found_any=false
    for lang in "${target_languages[@]}"; do
        if [[ -n "${lang_contents[$lang]}" ]]; then
            local output_file="$output_dir/$lang"
            printf '%s' "${lang_contents[$lang]}" > "$output_file"
            local line_count=$(echo -n "${lang_contents[$lang]}" | wc -l)
            echo "Created $lang with $line_count lines" >&2
            found_any=true
        fi
    done

    if [[ "$found_any" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

main() {
    declare -A packages
    packages["Microsoft.MinecraftUWP_8wekyb3d8bbwe"]="release"
    packages["Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"]="preview"

    target_languages=("en_US.lang" "zh_CN.lang" "zh_TW.lang")

    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    output_dir="$script_dir/../extracted"

    mkdir -p "$output_dir"

    for package_name in "${!packages[@]}"; do
        folder_name="${packages[$package_name]}"

        echo -e "\n\033[36mProcessing package: $package_name\033[0m"

        appx_file=$(get_appx_file "$package_name")
        if [[ $? -ne 0 || -z "$appx_file" ]]; then
            echo -e "\033[33mFailed to download appx file for $package_name\033[0m"
            continue
        fi

        package_output_dir="$output_dir/$folder_name"
        mkdir -p "$package_output_dir"

        if ! get_texts_from_zip "$appx_file" "$package_output_dir" "${target_languages[@]}"; then
            echo -e "\033[33mFailed to extract language files from $appx_file\033[0m"
            continue
        fi
    done

    echo -e "\n\033[32mLanguage file extraction completed!\033[0m"
    echo -e "\033[36mOutput directory: $(realpath "$output_dir")\033[0m"
}

main "$@"
