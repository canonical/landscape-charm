test:
	cd hooks && trial test_hooks.py

lint:
	bzr ls-lint
