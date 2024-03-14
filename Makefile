DIRNAME = $(notdir $(shell pwd))
DIRNAME := $(addsuffix -auto, $(DIRNAME))

build: clean
	charmcraft pack
	juju add-model $(DIRNAME)
	juju deploy ./bundle.yaml

clean:
	-rm *.charm
	-juju destroy-model -y $(DIRNAME) --force
