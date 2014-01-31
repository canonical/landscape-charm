test:
	cd hooks && trial test_hooks.py

stage-integration-test:
	@echo "** Note: config/repo-file & config/license-file must exist"
	cp -f config/repo-file config/license-file config/vhostssl.tmpl config/vhost.tmpl .

integration-test: stage-integration-test
	juju test -v --timeout 2000s

lint:
	find hooks -name *.py | xargs pyflakes
	pyflakes3 tests/*
