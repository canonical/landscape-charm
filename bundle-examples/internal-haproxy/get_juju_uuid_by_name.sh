#!/bin/bash
set -eux

input=$(cat)
_model_name=$(echo "$input" | jq -r '.model_name')
MODEL_NAME=${_model_name:-"landscape-charm-build"}
MODEL_UUID=$(juju models --format json | jq -r  --arg model_name "$MODEL_NAME" '.models[] | select(."short-name" == $model_name) | ."model-uuid"')

echo "{\"uuid\": \"$MODEL_UUID\"}"
