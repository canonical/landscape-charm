test:
	trial hooks

verify-juju-test:
	@echo "Checking for ... "
	@echo -n "juju-test: "
	@if [ -z `which juju-test` ]; then \
		echo -e "\nRun ./dev/ubuntu-deps to get the juju-test command installed"; \
		exit 1;\
	else \
		echo "installed"; \
	fi 

update-charm-revision-numbers:
	dev/update-charm-revision-numbers apache2 postgresql juju-gui haproxy rabbitmq-server nfs

integration-test: verify-juju-test config/repo-file config/license-file config/vhostssl.tmpl config/vhost.tmpl
	juju test -p SKIP_SLOW_TESTS,DEPLOYER_TARGET -v --timeout 3000s

lint:
	flake8 --exclude=charmhelpers hooks
	pyflakes3 tests/* dev/update-charm-revision-numbers
	find . -name *.py -print0 | xargs -0 pep8
	pep8 tests/* dev/update-charm-revision-numbers 

clean: clean-integration-test

.PHONY: lint \
	integration-test \
	verify-juju-test \
	test \
	clean \
	clean-integration-test \
	update-charm-revision-numbers
