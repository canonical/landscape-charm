PYTHON := /usr/bin/env python

test:
	trial lib
	# For now only the install hook runs against python3
	trial3 lib/tests/test_apt.py lib/tests/test_install.py

ci-test:
	./dev/ubuntu-deps
	$(MAKE) test lint

update-charm-revision-numbers: bundles
	@dev/update-charm-revision-numbers \
		$(EXTRA_UPDATE_ARGUMENTS) \
		apache2 postgresql juju-gui haproxy rabbitmq-server nfs

test-depends: bundles
	pip install --user bundletester juju-deployer
	pip3 install --user amulet
	cd tests && PYTHONPATH="~/.local/lib/python3.5/site-packages" python3 test_helpers.py

bundles-checkout:
	@if [ -d bundles ]; then \
	    bzr up bundles; \
	else \
	    bzr co lp:landscape-bundles bundles; \
	fi; \
	make -C bundles deps
	make -C bundles clean

bundles: bundles-checkout
	bundles/render-bundles

bundles-local-branch: bundles-checkout
	bundles/render-bundles --landscape-branch $(CURDIR)

bundles-local-charm: bundles-checkout
	bundles/render-bundles --landscape-charm $(CURDIR)

secrets:
	@if [ -d secrets ]; then \
	    bzr up secrets; \
	else \
	    bzr co lp:~landscape/landscape/secrets secrets; \
	fi

integration-test: test-depends
	~/.local/bin/bundletester --skip-implicit -t . -e 'localhost:'
	# juju test --set-e -p LS_CHARM_SOURCE,JUJU_HOME,JUJU_ENV,PG_MANUAL_TUNING,DENSE_MAAS -v --timeout 7200s

# Run integration tests using the LDS package from the lds-trunk PPA
integration-test-trunk: secrets
	LS_CHARM_SOURCE=lds-trunk-ppa $(MAKE) $(subst -trunk,,$@)

deploy-dense-maas: bundles-local-branch
	./dev/deployer dense-maas

deploy-dense-maas-dev: bundles-local-branch repo-file-trunk
	./dev/deployer dense-maas --flags juju-debug

deploy: bundles-local-branch
	./dev/deployer scalable

repo-file-trunk: secrets
	grep -e "^source:" secrets/lds-trunk-ppa | cut -f 2- -d " " > config/repo-file

lint:
	flake8 --filename='*' hooks
	flake8 lib tests
	pyflakes3 tests dev/update-charm-revision-numbers
	find . -name *.py -not -path "./old/*" -not -path "./build/*" -not -path "*/charmhelpers/*" -print0 | xargs -0 flake8
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
