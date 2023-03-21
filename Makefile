build: clean
	charmcraft pack
	juju add-model testserver
	juju deploy ./bundle.yaml

clean:
	-rm *.charm
	-juju destroy-model -y testserver --force
