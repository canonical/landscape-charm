.PHONY: test-charm-module \
	fmt-check \
	tflint-check \
	check-charm-module \
	fmt-fix \
	tflint-fix \
	fix-charm-module

test-charm-module:
	terraform init -backend=false && \
	terraform test

fmt-check:
	terraform init -backend=false && \
	terraform fmt -check -recursive

tflint-check:
	tflint --init && tflint --recursive

check-charm-module: fmt-check tflint-check

fmt-fix:
	terraform init -backend=false && \
	terraform fmt -recursive

tflint-fix:
	tflint --init && tflint --recursive --fix

fix-charm-module: fmt-fix tflint-fix
