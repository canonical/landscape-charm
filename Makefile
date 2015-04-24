#!/usr/bin/make
PYTHON := /usr/bin/env python

test:
	@cd hooks && trial lib

ci-test:
	./dev/ubuntu-deps
	$(MAKE) test

verify-juju-test:
	@echo "Checking for ... "
	@echo -n "juju-test: "
	@if [ -z `which juju-test` ]; then \
		echo -e "\nRun ./dev/ubuntu-deps to get the juju-test command installed"; \
		exit 1;\
	else \
		echo "installed"; \
	fi 

update-charm-revision-numbers: bundles
	@dev/update-charm-revision-numbers \
		$(EXTRA_UPDATE_ARGUMENTS) \
		apache2 postgresql juju-gui haproxy rabbitmq-server nfs

test-depends: verify-juju-test bundles

bundles:
	@if [ -d bundles ]; then \
	    bzr up bundles; \
	else \
	    bzr co lp:~landscape/landscape-charm/bundles-trunk-new-charm bundles; \
	fi

secrets:
	@if [ -d secrets ]; then \
	    bzr up secrets; \
	else \
	    bzr co lp:~landscape/landscape/secrets secrets; \
	fi

integration-test: test-depends
	juju test --set-e -p SKIP_SLOW_TESTS,LS_CHARM_SOURCE,JUJU_HOME,JUJU_ENV -v --timeout 3000s

integration-test-dense-maas: test-depends
	DEPLOYER_TARGET=landscape-dense-maas make integration-test

# Run integration tests using the LDS package from the lds-trunk PPA
integration-test-trunk: test-depends secrets
	LS_CHARM_SOURCE=lds-trunk-ppa make integration-test

deploy-dense-maas: test-depends
	SKIP_TESTS=1 DEPLOYER_TARGET=landscape-dense-maas tests/01-begin.py

deploy: test-depends
	SKIP_TESTS=1 DEPLOYER_TARGET=landscape-scalable tests/01-begin.py

lint:
	flake8 --exclude=charmhelpers hooks
	pyflakes3 tests dev/update-charm-revision-numbers
	find . -name *.py -not -path "./old/*" -not -path "*/charmhelpers/*" -print0 | xargs -0 pep8
	pep8 tests dev/update-charm-revision-numbers 

clean:
	@rm -rf bundles

.PHONY: lint \
	test-depends \
	deploy-dense-maas \
	integration-test \
	verify-juju-test \
	test \
	clean \
	update-charm-revision-numbers \
	bundles \
	deploy

dev/charm_helpers_sync.py:
	@mkdir -p dev
	@bzr cat lp:charm-helpers/tools/charm_helpers_sync/charm_helpers_sync.py \
        > dev/charm_helpers_sync.py

sync: dev/charm_helpers_sync.py
	$(PYTHON) dev/charm_helpers_sync.py -c charm-helpers.yaml
