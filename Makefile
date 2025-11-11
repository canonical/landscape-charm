DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/postgres16.bundle.yaml
PLATFORM ?= ubuntu@22.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false


.PHONY: build deploy clean terraform-dev

build:
	ccc pack --platform $(PLATFORM)

deploy:
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	@if [ "$(SKIP_BUILD)" != "true" ]; then $(MAKE) build; else echo "skipping build..."; fi
	juju add-model $(MODEL_NAME)
	juju deploy -m $(MODEL_NAME) $(BUNDLE_PATH)

clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage

# NOTE: we don't destroy the state with Terraform because
# the local charm dev will break the state anyways. 
	-cd terraform && rm -f terraform.tfstate* && \
		cd example && rm -f terraform.tfstate* && \
		cd ../..

# Unforunately, the Terraform provider for Juju does not support local charm dev, so this 
# is just using it as a data source.
# TODO: Update when the Terraform provider for Juju supports local charm dev (like bundles).
terraform-dev: deploy
	cd terraform/data && \
	terraform init && \
	terraform apply -auto-approve -var="model_name=$(MODEL_NAME)"
