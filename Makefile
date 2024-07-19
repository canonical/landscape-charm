DIRNAME = $(notdir $(shell pwd))
DIRNAME := $(addsuffix -build, $(DIRNAME))

build: clean
	charmcraft pack
	juju add-model $(DIRNAME)
	juju deploy ./bundle.yaml

clean:
	-rm *.charm
	-juju destroy-model --no-prompt $(DIRNAME) --force
