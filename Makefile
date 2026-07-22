# Docker is the primary dev loop: `make up` boots the whole stack.
# The uv venv lives OUTSIDE the repo (UV_PROJECT_ENVIRONMENT): on macOS with
# iCloud-synced folders, uv marks .venv files hidden and Python 3.13 silently
# skips hidden .pth files — an in-repo venv breaks imports.
export UV_PROJECT_ENVIRONMENT ?= $(HOME)/.venvs/cu-bootcamp-yadro
VENV    := $(UV_PROJECT_ENVIRONMENT)
COMPOSE := docker compose -f infra/docker-compose.yml

.PHONY: up down sync test contracts contracts-check

## --- the stack --------------------------------------------------------------
up:            ## build + start everything (frontend on :8080, api on :8000)
	$(COMPOSE) up --build -d

down:          ## stop everything (add V=1 to also drop volumes)
	$(COMPOSE) down $(if $(V),-v)

## --- local python (unit tests, contracts codegen) ---------------------------
sync:
	uv sync --all-packages

test: sync
	$(VENV)/bin/pytest -q

contracts: sync  ## regenerate schema + TS from the Pydantic source of truth
	$(VENV)/bin/python contracts/scripts/export_schema.py
	npx --yes json-schema-to-typescript@15 \
		-i contracts/schema/contracts.schema.json \
		-o contracts/generated/contracts.ts \
		--unreachableDefinitions --no-additionalProperties

contracts-check: contracts  ## CI gate: generated artifacts must be committed
	git diff --exit-code -- contracts/schema contracts/generated
