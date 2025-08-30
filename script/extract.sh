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

convert_lang_to_json() {
    local lang_content="$1"
    local output_file="$2"

    echo "$lang_content" | awk '
    BEGIN {
        print "{"
        first = 1
    }

    /^[[:space:]]*$/ || /^##/ {
        next
    }

    /^[^=]+=/ {
        eq_pos = index($0, "=")
        if (eq_pos > 0) {
            key = substr($0, 1, eq_pos - 1)
            value = substr($0, eq_pos + 1)

            gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)

            if (key in seen_keys) {
                next
            }
            seen_keys[key] = 1

            gsub(/\\/, "\\\\", key)
            gsub(/"/, "\\\"", key)
            gsub(/\\/, "\\\\", value)
            gsub(/"/, "\\\"", value)
            gsub(/\t/, "\\t", value)
            gsub(/\r/, "\\r", value)
            gsub(/\n/, "\\n", value)

            if (!first) print ","
            printf "  \"%s\": \"%s\"", key, value
            first = 0
        }
    }

    END {
        printf "\n}"
    }' > "$output_file"
}

extract_files_to_structure() {
    local zip_path="$1"
    local base_output_dir="$2"
    local target_languages=("${@:3}")

    echo "Extracting files to directory structure from $zip_path..." >&2

    local temp_dir=$(mktemp -d)

    if ! unzip -q "$zip_path" "data/resource_packs/*/texts/*.lang" -d "$temp_dir" 2>/dev/null; then
        echo "Warning: No language files found or extraction failed for $zip_path" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    local found_any=false
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

        if [[ "$is_target" == "false" || ! -s "$file" ]]; then
            continue
        fi

        echo "  Processing: $file" >&2

        local relative_path=$(echo "$file" | sed "s|^$temp_dir/data/resource_packs/||" | sed "s|/texts/|/|")
        local output_file="$base_output_dir/$relative_path"
        local output_dir=$(dirname "$output_file")

        mkdir -p "$output_dir"

        local cleaned_content
        cleaned_content=$(sed $'s/\xEF\xBB\xBF//; s/\r$//; /^[[:space:]]*$/d' "$file")

        if [[ -n "$cleaned_content" ]]; then
            printf '%s' "$cleaned_content" > "$output_file"
            echo "Created $relative_path" >&2

            local json_file="${output_file%.lang}.json"
            convert_lang_to_json "$cleaned_content" "$json_file"

            local json_entry_count=$(grep -c '".*":' "$json_file" 2>/dev/null || echo "0")
            echo "Created ${relative_path%.lang}.json with $json_entry_count entries" >&2

            found_any=true
        fi
    done

    rm -rf "$temp_dir"

    if [[ "$found_any" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

extract_release_files() {
    local zip_path="$1"
    local base_output_dir="$2"
    local target_languages=("${@:3}")

    echo "Extracting release files from $zip_path..." >&2

    local temp_dir=$(mktemp -d)

    if ! unzip -q "$zip_path" "data/resource_packs/*/texts/*.lang" -d "$temp_dir" 2>/dev/null; then
        echo "Warning: No language files found or extraction failed for $zip_path" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    local found_any=false
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

        if [[ "$is_target" == "false" || ! -s "$file" ]]; then
            continue
        fi

        local relative_path=$(echo "$file" | sed "s|^$temp_dir/data/resource_packs/||" | sed "s|/texts/|/|")

        if [[ "$relative_path" == *"beta/"* ]]; then
            echo "  Skipping beta path: $relative_path" >&2
            continue
        fi

        echo "  Processing: $file" >&2

        local output_file="$base_output_dir/$relative_path"
        local output_dir=$(dirname "$output_file")

        mkdir -p "$output_dir"

        local cleaned_content
        cleaned_content=$(sed $'s/\xEF\xBB\xBF//; s/\r$//; /^[[:space:]]*$/d' "$file")

        if [[ -n "$cleaned_content" ]]; then
            printf '%s' "$cleaned_content" > "$output_file"
            echo "Created $relative_path" >&2

            local json_file="${output_file%.lang}.json"
            convert_lang_to_json "$cleaned_content" "$json_file"

            local json_entry_count=$(grep -c '".*":' "$json_file" 2>/dev/null || echo "0")
            echo "Created ${relative_path%.lang}.json with $json_entry_count entries" >&2

            found_any=true
        fi
    done

    rm -rf "$temp_dir"

    if [[ "$found_any" == "true" ]]; then
        return 0
    else
        return 1
    fi
}

main() {
    declare -A packages
    packages["Microsoft.MinecraftUWP_8wekyb3d8bbwe"]="release"
    packages["Microsoft.MinecraftWindowsBeta_8wekyb3d8bbwe"]="development"

    target_languages=("en_US.lang" "zh_CN.lang" "zh_TW.lang")

    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    output_dir="$script_dir/../extracted"

    mkdir -p "$output_dir"

    local first_package=true
    for package_name in "${!packages[@]}"; do
        folder_name="${packages[$package_name]}"

        if [[ "$first_package" == "true" ]]; then
            echo -e "\033[36mProcessing package: $package_name\033[0m"
            first_package=false
        else
            echo -e "\n\033[36mProcessing package: $package_name\033[0m"
        fi

        appx_file=$(get_appx_file "$package_name")
        if [[ $? -ne 0 || -z "$appx_file" ]]; then
            echo -e "\033[33mFailed to download appx file for $package_name\033[0m"
            continue
        fi

        package_output_dir="$output_dir/$folder_name"
        mkdir -p "$package_output_dir"

        if [[ "$package_name" == "Microsoft.MinecraftUWP_8wekyb3d8bbwe" ]]; then
            if ! extract_release_files "$appx_file" "$package_output_dir" "${target_languages[@]}"; then
                echo -e "\033[33mFailed to extract language files from $appx_file\033[0m"
                continue
            fi
        else
            if ! extract_files_to_structure "$appx_file" "$package_output_dir" "${target_languages[@]}"; then
                echo -e "\033[33mFailed to extract language files from $appx_file\033[0m"
                continue
            fi
        fi
    done

    echo -e "\n\033[32mLanguage file extraction completed!\033[0m"
    echo -e "\033[36mOutput directory: $(realpath "$output_dir")\033[0m"
}

main "$@"
