include terraform/charm/Makefile
include terraform/product/Makefile

DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/postgres16.bundle.yaml
PLATFORM ?= ubuntu@24.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false

.PHONY: build \
	deploy \
	clean \
	test \
	integration-test \
	coverage \
	lint \
	terraform-check-all \
	terraform-fix-all \
	terraform-test-all

# Python testing and linting
test:
	poetry run pytest --tb native tests/unit

integration-test:
	poetry run pytest -v --tb native tests/integration

coverage:
	poetry run coverage run --branch --source=src -m pytest -v --tb native tests/unit
	poetry run coverage report -m

lint:
	poetry run flake8 src tests
	poetry run isort --check-only src tests
	poetry run black --check src tests
	poetry run ruff check src tests

fmt:
	poetry run isort src tests
	poetry run black src tests
	poetry run ruff check --fix src tests

# Charm building and deployment
build:
	poetry run ccc pack --platform $(PLATFORM)

deploy:
	@if [ "$(SKIP_CLEAN)" != "true" ]; then $(MAKE) clean; else echo "skipping clean..."; fi
	@if [ "$(SKIP_BUILD)" != "true" ]; then $(MAKE) build; else echo "skipping build..."; fi
	juju add-model $(MODEL_NAME)
	juju deploy -m $(MODEL_NAME) $(BUNDLE_PATH)

clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage

terraform-check-all:
	cd terraform/charm && $(MAKE) check-charm-module
	cd terraform/product && $(MAKE) check-product-modules

terraform-fix-all:
	cd terraform/charm && $(MAKE) fix-charm-module
	cd terraform/product && $(MAKE) fix-product-modules

terraform-test-all:
	cd terraform/charm && $(MAKE) test-charm-module
	cd terraform/product && $(MAKE) test-product-modules
