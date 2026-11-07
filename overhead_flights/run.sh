#!/usr/bin/with-contenv bashio
# with-contenv passes the Supervisor's environment (incl. SUPERVISOR_TOKEN) through to the app
bashio::log.info "Starting Overhead Flights"
exec python3 -u /app/app.py
