# The commands agents and people use most. Each target runs the real script, so
# these stay short. `make` lists them.
.DEFAULT_GOAL := help
.PHONY: help mqtt-clean mqtt-watch wt wt-sweep check remote portal-check panels desks panelpro-test docs-index publications waybills submodules tables-pull tables-pull-pi ops-pull sts-pull shot deploy-layout deploy-all deploy-status redeploy deploy-site

help:  ## List the commands
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 16

wt:  ## Start a task in its own worktree: make wt TOPIC=short-topic
	@python3 tools/agent/worktrees.py new $(TOPIC) --agent $(or $(AGENT),claude)

wt-sweep:  ## Remove agent worktrees whose PR is merged
	python3 tools/agent/worktrees.py sweep

check:  ## Run every repo check
	./tools/check.sh

remote:  ## Run a command on the Windows box's WSL (pushed branch): make remote CMD="./tools/check.sh"
	@test -n "$(CMD)" || { echo 'make remote: set CMD="..."' >&2; exit 2; }
	./tools/hosts/win_run.sh -- bash -c '$(subst ','"'"',$(CMD))'

portal-check:  ## Build the website and test its links
	python3 www/scripts/check_portal_build.py

panels:  ## Rebuild every panel drawn from the schematic, in order (CHECK=1 only checks)
	./tools/schematic/build_panels.sh $(if $(filter 1 yes true,$(CHECK)),--check) $(if $(filter 1 yes true,$(FULL)),--full)

wiring-freeze:  ## Freeze a main or upper control point's wiring into wiring.csv once it is wired: make wiring-freeze CP="CP 107"
	python3 tools/wiring/freeze_wiring.py --cp "$(CP)"
	python3 tools/schematic/build_device_map.py --check

desks:  ## Rebuild and validate the CATS desks (generated from the schematic)
	python3 tools/schematic/build_cats_panel.py
	python3 cats/scripts/validate_cats_panel.py

panelpro-test:  ## Load tables.xml in real PanelPro on this Mac
	./jmri/layouts/hart/scripts/run_panelpro_smoke_test.sh

docs-index:  ## Rebuild docs/INDEX.md
	python3 tools/ops/build_docs_index.py

tables-pull:  ## Keep a Mac PanelPro Store in media/pulled-stores in the main checkout for tools/schematic/split_store.py (tables.xml is generated)
	./tools/ops/pull_tables.sh

tables-pull-pi:  ## Keep a Pi PanelPro Store in media/pulled-stores in the main checkout for tools/schematic/split_store.py (tables.xml is generated)
	./tools/ops/pull_tables_pi.sh

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

mqtt-clean:  ## Clear the retained MQTT junk topics clear_mqtt_cmd_sensor_retain.py lists (_discard included) on the layout broker
	python3 tools/mqtt/clear_mqtt_cmd_sensor_retain.py

mqtt-watch:  ## Watch _discard writes on the layout broker with timestamps, read-only (Ctrl-C stops): run it while testing
	python3 tools/mqtt/watch_discard.py

deploy-layout:  ## Deploy to the Pi and Windows (kept on the same commit)
	./tools/hosts/sync_hart_package.sh --pi --win

deploy-all:  ## Deploy to every layout host
	./tools/hosts/sync_hart_package.sh --all

deploy-status:  ## Show which commit each layout host last got: make deploy-status HOSTS="--pi --win"
	./tools/hosts/deploy_status.sh $(HOSTS)

redeploy:  ## Redeploy an older commit (rollback): make redeploy COMMIT=<sha> HOSTS="--pi --win"
	@test -n "$(COMMIT)" || { echo 'make redeploy COMMIT=<sha> HOSTS="--pi --win" (or --pi, --win, --all, --mac)'; exit 2; }
	./tools/hosts/redeploy_commit.sh $(COMMIT) $(HOSTS)

deploy-site:  ## Deploy www.hartrailroad.com
	./www/scripts/deploy_hartrailroad.sh
