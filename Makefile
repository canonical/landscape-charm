.PHONY: test lint
test:
	trial hooks

lint:
	@flake8 --exclude hooks/charmhelpers hooks
