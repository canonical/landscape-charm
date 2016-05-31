PYTHON := /usr/bin/env python

test:
	trial lib
	# For now only the install hook runs against python3
	trial3 lib/tests/test_apt.py lib/tests/test_install.py

ci-test:
	./dev/ubuntu-deps
	$(MAKE) test lint

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
	@cd tests && python3 test_helpers.py

bundles:
	@if [ -d bundles ]; then \
	    bzr up bundles; \
	else \
	    bzr co lp:~landscape/landscape-charm/bundles-trunk bundles; \
	fi; \
	make -C bundles render;

secrets:
	@if [ -d secrets ]; then \
	    bzr up secrets; \
	else \
	    bzr co lp:~landscape/landscape/secrets secrets; \
	fi

integration-test: test-depends
	juju test --set-e -p LS_CHARM_SOURCE,JUJU_HOME,JUJU_ENV,PG_MANUAL_TUNING -v --timeout 3000s

# Run integration tests using the LDS package from the lds-trunk PPA
integration-test-trunk: secrets
	LS_CHARM_SOURCE=lds-trunk-ppa $(MAKE) $(subst -trunk,,$@)

deploy-dense-maas: bundles
	./dev/deployer dense-maas

deploy-dense-maas-dev: bundles
	./dev/deployer dense-maas --flags juju-debug

deploy: bundles
	./dev/deployer scalable

repo-file-trunk: secrets
	grep -e "^source:" secrets/lds-trunk-ppa | cut -f 2- -d " " > config/repo-file

lint:
	flake8 --filename='*' hooks
	flake8 lib tests
	pyflakes3 tests dev/update-charm-revision-numbers
	find . -name *.py -not -path "./old/*" -not -path "*/charmhelpers/*" -print0 | xargs -0 flake8
	flake8 tests dev/update-charm-revision-numbers

clean:
	@rm -rf bundles
	@find -name '*.pyc' -delete

.PHONY: lint \
	test-depends \
	deploy-dense-maas \
	deploy-dense-maas-dev \
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

build: secrets test-depends

.DEFAULT_GOAL := build
