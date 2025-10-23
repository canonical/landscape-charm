DIRNAME = $(notdir $(shell pwd))
DIRNAME := $(addsuffix -build, $(DIRNAME))

build:
	ccc pack --platform ubuntu@24.04:amd64

deploy: clean build
	juju add-model $(DIRNAME)
	juju deploy -m $(DIRNAME) ./bundle-examples/bundle.yaml

clean:
	-rm -f *.charm
	-juju destroy-model --no-prompt $(DIRNAME) \
		--force --no-wait --destroy-storage
