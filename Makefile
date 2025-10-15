DIRNAME = $(notdir $(shell pwd))
DIRNAME := $(addsuffix -build, $(DIRNAME))

build: clean
	ccc pack
	juju add-model $(DIRNAME)
	juju deploy ./bundle-examples/bundle.yaml

clean:
	-rm *.charm
	-juju destroy-model --no-prompt $(DIRNAME) --force
