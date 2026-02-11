DIR_NAME := $(notdir $(shell pwd))
BUNDLE_PATH ?= ./bundle-examples/internal-haproxy/internal-haproxy.bundle.yaml
PLATFORM ?= ubuntu@24.04:amd64
MODEL_NAME ?= $(DIR_NAME)-build
LBAAS_MODEL_NAME ?= lbaas
CLEAN_PLATFORM := $(subst :,-,$(PLATFORM))
SKIP_BUILD ?= false
SKIP_CLEAN ?= false


.PHONY: build deploy lbaas clean clean-lbaas test integration-test coverage lint fmt terraform-test fmt-check tflint-check terraform-check fmt-fix tflint-fix terraform-fix

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

install-terraform:
	@if command -v terraform >/dev/null; then \
		echo "Terraform is already installed, skipping install..."; \
	else \
		echo "Installing Terraform..."; \
		snap install terraform --classic; \
	fi

clean-lbaas:
	-juju destroy-model --no-prompt $(LBAAS_MODEL_NAME) \
		--force --no-wait --destroy-storage
	-cd bundle-examples/internal-haproxy && \
	rm -rf *.tfstate && \
	cd ../..


lbaas: clean-lbaas install-terraform deploy
	cd bundle-examples/internal-haproxy && \
	terraform init && \
	terraform apply -auto-approve \
		-var model_name=$(MODEL_NAME) \
		-var lbaas_model_name=$(LBAAS_MODEL_NAME)


terraform-test: install-terraform
	cd terraform && \
	terraform init -backend=false && \
	terraform test

fmt-check: install-terraform
	cd terraform && \
	terraform init -backend=false && \
	terraform fmt -check -recursive

tflint-check: install-terraform
	cd terraform && tflint --init && tflint --recursive

terraform-check: fmt-check tflint-check

fmt-fix:
	cd terraform && \
	terraform init -backend=false && \
	terraform fmt -recursive

tflint-fix: install-terraform
	cd terraform && tflint --init && tflint --recursive --fix

terraform-fix: fmt-fix tflint-fix

clean:
	-rm -f landscape-server_$(CLEAN_PLATFORM).charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage
