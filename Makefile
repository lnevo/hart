# The commands agents and people use most. Each target runs the real script, so
# these stay short. `make` lists them.
.DEFAULT_GOAL := help
.PHONY: help mqtt-clean mqtt-watch wt wt-sweep orient status check static baselines pr-kind ready remote portal-check panels desks panelpro-test timings docs-index map site-data publications waybills submodules tables-pull tables-pull-pi ops-pull roster-pull sts-pull shot deploy-layout deploy-all deploy-status backup-status redeploy deploy-site speedmatch

help:  ## List the commands
	@grep -hE '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/:.*## /\t/' | expand -t 16

wt:  ## Start a task in its own worktree: make wt TOPIC=short-topic
	@python3 tools/agent/worktrees.py new $(TOPIC) --agent $(or $(AGENT),claude)

wt-sweep:  ## Remove agent worktrees whose PR is merged
	python3 tools/agent/worktrees.py sweep

orient:  ## Who works on what: claims, worktrees in progress, operating flag, last deploys, open PRs, what waits to be pulled in
	@python3 tools/ops/orient.py

status:  ## Build wiki/STATUS.md (gitignored) from the entry files in wiki/status/, with the Counts line (ADR-038)
	@python3 tools/ops/status_counts.py

check:  ## Run every repo check
	./tools/check.sh

static:  ## Quick local checks before a push or make remote: check.sh's static group, less the panels-* jobs (about 20 s warm)
	CHECK_ONLY="^($$(python3 tools/pipeline/manifest.py jobs check --group static | awk '{print $$1}' | grep -v '^panels-' | paste -sd'|' -))$$" ./tools/check.sh

baselines:  ## The queue holder's wave-end sweep PR: lower the mypy, habits and hand tables baselines with --update; py sizes --update only drops rows of files gone or at or under their limit
	python3 tools/audit/check_mypy.py --update
	python3 tools/audit/check_habits.py --update
	python3 tools/audit/check_py_sizes.py --update
	python3 tools/audit/check_hand_tables.py --update

pr-kind:  ## Does this branch need make remote? Prints docs, light (make static and the light checks, no make remote) or full, with the reason
	@python3 tools/ci/changed_kind.py --git

ready:  ## Ship a lane's work from its worktree: make ready FILES="a b" MSG="..." [TITLE=...] [BODY=... | BODY_FILE=path]; commit, checks, push, make remote unless light, PR (never merges)
	@python3 tools/agent/ready.py --files '$(subst ','"'"',$(FILES))' --msg '$(subst ','"'"',$(MSG))' --title '$(subst ','"'"',$(TITLE))' \
	  --body '$(subst ','"'"',$(BODY))' --body-file '$(subst ','"'"',$(BODY_FILE))'

remote:  ## Run a command on the Windows box's WSL (pushed branch): make remote CMD="./tools/check.sh"
	@test -n "$(CMD)" || { echo 'make remote: set CMD="..."' >&2; exit 2; }
	./tools/hosts/win_run.sh -- bash -c '$(subst ','"'"',$(CMD))'

portal-check:  ## Build the website and test its links
	python3 www/scripts/check_portal_build.py

panels:  ## Rebuild every panel drawn from the schematic, in order (CHECK=1 only checks)
	./tools/schematic/build_panels.sh $(if $(filter 1 yes true,$(CHECK)),--check) $(if $(filter 1 yes true,$(FULL)),--full)

timings:  ## Summarize the local step-timings log (make panels, check.sh) into docs/pipeline-map/timings.json
	python3 tools/pipeline/timings.py summarize

wiring-freeze:  ## Freeze a main or upper control point's wiring into wiring.csv once it is wired: make wiring-freeze CP="CP 107"
	python3 tools/wiring/freeze_wiring.py --cp "$(CP)"
	python3 tools/schematic/build_device_map.py --check

desks:  ## Rebuild the CATS desks (generated from the schematic)
	python3 tools/schematic/build_cats_panel.py

panelpro-test:  ## Load tables.xml in real PanelPro on this Mac
	./jmri/layouts/hart/scripts/run_panelpro_smoke_test.sh

docs-index:  ## Rebuild docs/INDEX.md
	python3 tools/ops/build_docs_index.py

map:  ## Build the pipeline map pages to view locally (not committed, ADR-036): docs/pipeline-map/index.html and www/library/pipeline-map.html
	python3 tools/ops/build_pipeline_map.py

site-data:  ## Build every file the site build makes instead of committing (ADR-036) into www/ for the local preview: the map page and the generated JSON (serve_portal.py does this at start)
	python3 www/scripts/site_views.py

tables-pull:  ## Keep a Mac PanelPro Store in media/pulled-stores in the main checkout for tools/schematic/split_store.py (tables.xml is generated)
	./tools/ops/pull_tables.sh

tables-pull-pi:  ## Keep a Pi PanelPro Store in media/pulled-stores in the main checkout for tools/schematic/split_store.py (tables.xml is generated)
	./tools/ops/pull_tables_pi.sh

ops-pull:  ## Bring Pi Operations Pro session state into the repo
	./tools/ops/pull_ops.sh

roster-pull:  ## Bring the Pi's DecoderPro roster into the repo master (jmri/layouts/hart/roster)
	./tools/ops/pull_roster.sh

sts-pull:  ## Copy the live STS backups and a database dump off the Pi
	./tools/hosts/pi_sts_pull_backups.sh

publications:  ## Regenerate docs/ops from hart-ops
	./tools/ops/rebuild_publications.sh

waybills:  ## Regenerate the blank car-card template and the spot waybill deck
	./ops/packages/car-cards/run_generate_print.sh

submodules:  ## Check out every external/ submodule at the commit hart records
	git submodule update --init --recursive

speedmatch:  ## Speed-matching tools in one command: make speedmatch ARGS="pom proposal.json" (ARGS="--help" lists them)
	python3 jmri/layouts/hart/scripts/speedmatch/speedmatch.py $(ARGS)

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

backup-status:  ## When the Pi and Windows backups last ran in full (ADR-035)
	@./tools/hosts/backup_launchagents.sh status

deploy-status:  ## Show which commit each layout host last got: make deploy-status HOSTS="--pi --win"
	./tools/hosts/deploy_status.sh $(HOSTS)

redeploy:  ## Redeploy an older commit (rollback): make redeploy COMMIT=<sha> HOSTS="--pi --win"
	@test -n "$(COMMIT)" || { echo 'make redeploy COMMIT=<sha> HOSTS="--pi --win" (or --pi, --win, --all, --mac)'; exit 2; }
	./tools/hosts/redeploy_commit.sh $(COMMIT) $(HOSTS)

deploy-site:  ## Deploy www.hartrailroad.com
	./www/scripts/deploy_hartrailroad.sh
