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
	@if echo 'import amulet' | python2; then \
		echo "installed"; \
	else \
		echo "\nRun ./dev/install-amulet to get the juju-test command installed"; \
		exit 1;\
	fi 

stage-integration-test: config/repo-file config/license-file
	cp -f config/repo-file config/license-file config/vhostssl.tmpl config/vhost.tmpl .

integration-test: verify-juju-test stage-integration-test
	juju test -v --timeout 2000s

lint:
	flake8 --exclude=charmhelpers hooks
	pyflakes3 tests/*

.PHONY: lint integration-test stage-integration-test verify-juju-test test
