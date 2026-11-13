# The commands agents and people use most. Each target runs the real script, so
# these stay short. `make` lists them.
.DEFAULT_GOAL := help
.PHONY: help wt wt-sweep check portal-check desks panelpro-test docs-index publications waybills submodules tables-pull ops-pull sts-pull shot deploy-layout deploy-all deploy-status deploy-site

help:  ## List the commands
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 16

wt:  ## Start a task in its own worktree: make wt TOPIC=short-topic
	@python3 tools/agent/worktrees.py new $(TOPIC) --agent $(or $(AGENT),claude)

wt-sweep:  ## Remove agent worktrees whose PR is merged
	python3 tools/agent/worktrees.py sweep

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

ops-pull:  ## Bring Pi Operations Pro session state into the repo
	./tools/ops/pull_ops.sh

sts-pull:  ## Copy the live STS backups and a database dump off the Pi
	./tools/hosts/pi_sts_pull_backups.sh

publications:  ## Regenerate docs/ops from hart-ops
	./tools/ops/rebuild_publications.sh

waybills:  ## Regenerate the blank car-card template and the spot waybill deck
	./ops/packages/car-cards/run_generate_print.sh

submodules:  ## Check out every external/ submodule at the commit hart records
	git submodule update --init --recursive

shot:  ## Screenshot a page: make shot PAGE=www/index.html
	python3 tools/ops/screenshot.py $(PAGE)

deploy-layout:  ## Deploy to the Pi
	./tools/hosts/sync_hart_package.sh --pi

deploy-all:  ## Deploy to every layout host
	./tools/hosts/sync_hart_package.sh --all

deploy-status:  ## Show which commit each layout host last got: make deploy-status HOSTS="--pi --win"
	./tools/hosts/deploy_status.sh $(HOSTS)

deploy-site:  ## Deploy www.hartrailroad.com
	./www/scripts/deploy_hartrailroad.sh
