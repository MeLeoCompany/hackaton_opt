#!/bin/sh
set -eu

source_path=${R5_OSM_SOURCE:-/source/central-fed-district-latest.osm.pbf}
output_path=${R5_OSM_OUTPUT:-/output/moscow-region.osm.pbf}
bbox=${R5_OSM_BBOX:-35.0,54.1,41.0,57.0}
wait_seconds=${R5_SOURCE_WAIT_SECONDS:-900}

# Файл кладёт valhalla, и на свежем сервере он качается несколько минут. Ждём не просто
# появления файла, а целого PBF: у недокачанного osmium честно скажет «unexpected EOF»
elapsed=0
while ! osmium fileinfo "$source_path" > /dev/null 2>&1; do
    if [ "$elapsed" -ge "$wait_seconds" ]; then
        if [ -s "$source_path" ]; then
            echo "Исходный PBF так и не докачался за ${wait_seconds} с: $source_path" >&2
            echo "Это файл valhalla — смотрите docker compose logs valhalla" >&2
        else
            echo "Не найден исходный PBF: $source_path" >&2
        fi
        exit 1
    fi
    if [ $((elapsed % 60)) -eq 0 ]; then
        echo "Жду исходный PBF (качает valhalla), прошло ${elapsed} с из ${wait_seconds}"
    fi
    sleep 5
    elapsed=$((elapsed + 5))
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
