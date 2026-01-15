#!/bin/bash

ssh_public_keys=("${HOME}"/.ssh/id_*.pub)

first_key_path="${ssh_public_keys[0]}"

if [ ! -f "$first_key_path" ]; then
    echo "Error: No SSH public key found at $HOME/.ssh/id_*.pub" >&2
    exit 1
fi

key_content=$(cat "$first_key_path")

echo "{\"key\": \"${key_content}\"}"
