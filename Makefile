# The commands agents and people use most. Each target runs the real script, so
# these stay short. `make` lists them.
.DEFAULT_GOAL := help
.PHONY: help check portal-check desks panelpro-test docs-index publications tables-pull shot deploy-layout deploy-all deploy-site

help:  ## List the commands
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 16

check:  ## Run every repo check
	./tools/check.sh

portal-check:  ## Build the website and test its links
	python3 www/scripts/check_portal_build.py

desks:  ## Rebuild and validate the CATS desks
	python3 cats/scripts/wire_digicon.py
	python3 cats/scripts/validate_cats_panel.py

panelpro-test:  ## Load tables.xml in real PanelPro on this Mac
	./jmri/layouts/hart/scripts/run_panelpro_smoke_test.sh

docs-index:  ## Rebuild docs/INDEX.md
	python3 tools/ops/build_docs_index.py

tables-pull:  ## Bring a PanelPro Store from JMRI_UserFiles into the repo
	./tools/ops/pull_tables.sh

publications:  ## Regenerate docs/ops from hart-ops
	./tools/ops/rebuild_publications.sh

shot:  ## Screenshot a page: make shot PAGE=www/index.html
	python3 tools/ops/screenshot.py $(PAGE)

deploy-layout:  ## Deploy to the Pi
	./cats/scripts/sync_hart_package.sh --pi

deploy-all:  ## Deploy to every layout host
	./cats/scripts/sync_hart_package.sh --all

deploy-site:  ## Deploy www.hartrailroad.com
	./www/scripts/deploy_hartrailroad.sh
