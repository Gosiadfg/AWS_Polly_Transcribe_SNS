FILENAME=$(basename $2)
ENCODED=$(base64 -i $2)
TEXT=$(cat $2)
JSON="{\"file\": \"$ENCODED\", \"name\": \"$FILENAME\", \"text\": \"$TEXT\"}"
curl -XPOST -d "$JSON" -H "Content-type: application/json" -v $1