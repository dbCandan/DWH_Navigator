#!/bin/sh
set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# application-foundation/PRDs/001-user-accounts Requirement 14: no software version in Server. The
# server's own access log would write raw paths and query strings (rules/25); the application's
# request.completed event is the access log.
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header --no-access-log --reload
