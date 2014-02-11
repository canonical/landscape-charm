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
		echo "\nRun ./dev/install-amulet to get the juju-test command installed"; \
		exit 1;\
	fi 

repo-file:
	cp -f config/repo-file repo-file

license-file:
	cp -f config/license-file license-file

vhostssl.tmpl:
	cp -f config/vhostssl.tmpl vhostssl.tmpl

vhost.tmpl:
	cp -f config/vhost.tmpl vhost.tmpl

test-config.yaml: repo-file license-file vhostssl.tmpl vhost.tmpl
	dev/make-test-config config/landscape-deployments.cfg > test-config.yaml

stage-integration-test: config/repo-file config/license-file test-config.yaml

clean-integration-test:
	rm -f repo-file license-file test-config.yaml vhostssl.tmpl vhost.tmpl

integration-test: verify-juju-test stage-integration-test
	juju test -v --timeout 2000s

lint:
	flake8 --exclude=charmhelpers hooks
	pyflakes3 tests/*

clean: clean-integration-test

.PHONY: lint integration-test stage-integration-test verify-juju-test test clean clean-integration-test
