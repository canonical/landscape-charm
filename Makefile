DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/postgres16.bundle.yaml
PLATFORM ?= ubuntu@22.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false


.PHONY: build deploy clean

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
