#!/bin/sh
set -eu

source_path=${R5_OSM_SOURCE:-/source/central-fed-district-latest.osm.pbf}
output_path=${R5_OSM_OUTPUT:-/output/moscow-region.osm.pbf}
bbox=${R5_OSM_BBOX:-35.0,54.1,41.0,57.0}
wait_seconds=${R5_SOURCE_WAIT_SECONDS:-900}

elapsed=0
while [ ! -s "$source_path" ]; do
    if [ "$elapsed" -ge "$wait_seconds" ]; then
        echo "Не найден исходный PBF: $source_path" >&2
        exit 1
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ -s "$output_path" ]; then
    echo "Экстракт R5 уже существует: $output_path"
    exit 0
fi

temporary_path="${output_path}.part"
echo "Создаю экстракт R5 для bbox=$bbox"
osmium extract \
    --bbox "$bbox" \
    --strategy complete_ways \
    --overwrite \
    --output-format pbf \
    --output "$temporary_path" \
    "$source_path"
mv "$temporary_path" "$output_path"
echo "Экстракт R5 готов: $output_path"
