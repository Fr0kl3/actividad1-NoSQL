#!/usr/bin/env bash
set -euo pipefail

ES="http://localhost:9200"
AUTH="elastic:Elastic123"
echo "Esperando a Elasticsearch..."
until curl -s -u "&AUTH" "$ES/_cluster/health" > /dev/null; do
  sleep 3
done

curl -s -u "$AUTH" -X POST "$ES/_bulk?refresh=true" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @- <<'EOF'
{ "index": { "_index": "articulos", "_id": "1" } }
{ "titulo": "Teclado mecánico", "categoria": "periféricos", "precio": 59.90 }
{ "index": { "_index": "articulos", "_id": "2" } }
{ "titulo": "Ratón inalámbrico", "categoria": "periféricos", "precio": 24.50 }
{ "index": { "_index": "articulos", "_id": "3" } }
{ "titulo": "Monitor 27 pulgadas", "categoria": "pantallas", "precio": 189.00 }
EOF

echo
curl -s -u "$AUTH" "$ES/articulos/_count?pretty"
