test:
	trial hooks

verify-juju-test:
	@echo "Checking for ... "
	@echo -n "juju-test: "
	@if [ -z `which juju-test` ]; then \
		echo "\nRun ./dev/install-amulet to get the juju-test command installed"; \
		exit 1;\
	else \
		echo "installed"; \
	fi 
	@echo -n "amulet: "
	@if echo 'import amulet' | python3; then \
		echo "installed"; \
	else \
		echo "\nRun ./dev/install-amulet to get the amulet library installed"; \
		exit 1;\
	fi 

test-config.yaml: config/repo-file config/license-file config/vhostssl.tmpl config/vhost.tmpl
	cd config; ../dev/make-test-config landscape-deployments.yaml > ../test-config.yaml

stage-integration-test: test-config.yaml

integration-test: verify-juju-test stage-integration-test
	juju test -v --timeout 2000s

lint:
	flake8 --exclude=charmhelpers hooks
	pyflakes3 tests/*

clean: clean-integration-test

.PHONY: lint integration-test stage-integration-test verify-juju-test test clean clean-integration-test
