DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/postgres16.bundle.yaml
PLATFORM ?= ubuntu@22.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false


.PHONY: build deploy clean terraform-test fmt-check tflint-check terraform-check fmt-fix tflint-fix terraform-fix

build:
	ccc pack --platform $(PLATFORM)

deploy:
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	@if [ "$(SKIP_BUILD)" != "true" ]; then $(MAKE) build; else echo "skipping build..."; fi
	juju add-model $(MODEL_NAME)
	juju deploy -m $(MODEL_NAME) $(BUNDLE_PATH)

terraform-test:
	cd terraform && \
	terraform init -backend=false && \
	terraform test

fmt-check:
	cd terraform && \
	terraform init -backend=false && \
	terraform fmt -check -recursive

tflint-check:
	cd terraform && tflint --init && tflint --recursive

terraform-check: fmt-check tflint-check

fmt-fix:
	cd terraform && \
	terraform init -backend=false && \
	terraform fmt -recursive

tflint-fix:
	cd terraform && tflint --init && tflint --recursive --fix

terraform-fix: fmt-fix tflint-fix

clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage
