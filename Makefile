DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/bundle.yaml
PLATFORM ?= ubuntu@22.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))

.PHONY: build deploy clean

build:
	ccc pack --platform $(PLATFORM)

deploy: clean build
	juju add-model $(MODEL_NAME)
	juju deploy -m $(MODEL_NAME) $(BUNDLE_PATH)

clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage
	-rm *.charm
	-juju destroy-model --no-prompt $(DIRNAME) --force

# Unforunately, the Terraform provider for Juju does not support local charm dev...
# To avoid having to publish to test the charm module, this make recipe makes ends meet.
# TODO: Remove when The Terraform provider for Juju supports local charm dev (like bundles).
.PHONY: terraform-dev
terraform-dev: clean
	cd terraform/example && \
	terraform init -upgrade && \
	terraform apply -auto-approve -var="new_model_name=$(MODEL_NAME)"
