.PHONY: help reset-local-data

LOCAL_DATA_DIR := $(CURDIR)/data
LOCAL_STORAGE_DIR := $(CURDIR)/storage

help:
	@echo "Available commands:"
	@echo "  make reset-local-data CONFIRM=DELETE  Remove the local database and stored case files"

reset-local-data:
	@if [ "$(CONFIRM)" != "DELETE" ]; then \
		echo "Refusing to delete local data without explicit confirmation."; \
		echo "Stop Flask and the worker, then run: make reset-local-data CONFIRM=DELETE"; \
		exit 1; \
	fi
	@if [ "$(CURDIR)" = "/" ] || [ ! -f "$(CURDIR)/manage.py" ] || [ ! -f "$(CURDIR)/app/schema.sql" ]; then \
		echo "Safety check failed: run this target from the project root."; \
		exit 1; \
	fi
	@if command -v lsof >/dev/null 2>&1 && [ -f "$(LOCAL_DATA_DIR)/app.db" ] && lsof "$(LOCAL_DATA_DIR)/app.db" >/dev/null 2>&1; then \
		echo "The database is still open. Stop Flask and the background worker first."; \
		exit 1; \
	fi
	@rm -rf -- "$(LOCAL_DATA_DIR)" "$(LOCAL_STORAGE_DIR)"
	@mkdir -p "$(LOCAL_DATA_DIR)" "$(LOCAL_STORAGE_DIR)"
	@echo "Local database and case storage removed. Backups were not deleted."
	@echo "Next: python manage.py create-admin --username admin --full-name \"Clinical Administrator\""
