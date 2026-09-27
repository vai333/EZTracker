API=apps/api
WEB=apps/web
PY=$(API)/.venv/bin/python

.PHONY: keygen keygen-jwt install api web test test-integration lint discover contrast connect seed e2e create-user reset-password

keygen:  ## print a fresh Fernet key for CREDENTIALS_ENCRYPTION_KEY
	@$(PY) -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

install:
	$(PY) -m pip install -e "$(API)[dev]"
	$(PY) -m playwright install chromium
	cd $(WEB) && npm install

api:
	cd $(API) && .venv/bin/uvicorn eztracker.main:app --reload --port 8000 --env-file ../../.env

web:
	cd $(WEB) && npm run dev

test:
	cd $(API) && .venv/bin/pytest -q
	cd $(WEB) && npm test -- --run

lint:
	cd $(API) && .venv/bin/ruff check . && .venv/bin/mypy eztracker
	cd $(WEB) && npm run lint && npx tsc --noEmit

contrast:
	cd $(WEB) && npm run check:contrast

discover:  ## log in to Nexus with NEXUS_EMAIL/NEXUS_PASSWORD and write docs/nexus_api_map.md
	cd $(API) && set -a && . ../../.env && set +a && .venv/bin/python -m eztracker.scraper.discovery

test-integration:  ## DB + API tests against Atlas in a throwaway database (dropped afterwards)
	cd $(API) && set -a && . ../../.env && set +a && EZ_TEST_MONGO=1 .venv/bin/pytest -q tests/test_integration_db.py tests/test_api.py

keygen-jwt:  ## print a fresh AUTH_JWT_SECRET
	@$(PY) -c "import secrets; print(secrets.token_urlsafe(48))"

create-user:  ## create the single owner account: make create-user EMAIL=you@example.com (prompts for password)
	cd $(API) && .venv/bin/python -m eztracker.users create --email $(EMAIL)

reset-password:
	cd $(API) && .venv/bin/python -m eztracker.users reset --email $(EMAIL)

connect:  ## sign in to Nexus yourself in a visible browser (SSO/MFA path); USER_ID=<uid> also stores it
	cd $(API) && .venv/bin/python -m eztracker.scraper.connect $(if $(USER_ID),--user-id $(USER_ID)) $(if $(EMAIL),--email $(EMAIL))

seed:  ## load fixture data for UI dev into DATABASE_URL for USER_ID=<uid>
	cd $(API) && .venv/bin/python -m eztracker.seed --user-id $(USER_ID)

e2e:
	cd $(WEB) && npx playwright test
