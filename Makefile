DIRNAME ?= $(addsuffix -build, $(notdir $(shell pwd)))
MODEL_NAME = $(or $(LANDSCAPE_CHARM_JUJU_MODEL_NAME),$(DIRNAME))

build:
	ccc pack --platform ubuntu@22.04:amd64

deploy: clean build
	juju add-model $(MODEL_NAME)
	juju deploy -m $(MODEL_NAME) ./bundle-examples/bundle.yaml

clean:
	-rm -f *.charm
	-juju destroy-model --no-prompt $(MODEL_NAME) \
		--force --no-wait --destroy-storage

lint:
	-tox -e fmt
	-tox -e lint

unit-test:
	-tox -e unit

integration-test:
	-tox -e integration

check: deploy lint unit-test
	LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 $(MAKE) integration-test
	$(MAKE) clean
