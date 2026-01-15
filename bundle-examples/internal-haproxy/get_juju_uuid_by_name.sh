#!/bin/bash
_MODEL_NAME=${MODEL_NAME:-"landscape-charm-build"}
MODEL_UUID=$(juju models --format json | jq -r  --arg model_name "$_MODEL_NAME" '.models[] | select(."short-name" == $model_name) | ."model-uuid"')

echo "{\"uuid\": \"$MODEL_UUID\"}"
