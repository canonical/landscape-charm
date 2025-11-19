DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/legacy.bundle.yaml
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
