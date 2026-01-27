MODULE_PATHS := modules/landscape-scalable

.PHONY: check-product-modules fix-product-modules test-product-modules

check-product-modules:
	tflint --init
	for m in $(MODULE_PATHS); do \
		cd $$m && \
		terraform init -backend=false && \
		terraform fmt -check -recursive && \
		tflint --recursive; \
	done

fix-product-modules:
	tflint --init
	for m in $(MODULE_PATHS); do \
		cd $$m && \
		terraform init -backend=false && \
		terraform fmt -recursive && \
		tflint --recursive --fix; \
	done

test-product-modules:
	for m in $(MODULE_PATHS); do \
		cd $$m && \
		terraform init -backend=false && \
		terraform test; \
	done
