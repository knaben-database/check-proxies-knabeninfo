import os
import subprocess
import base64
from urllib.parse import urlparse


check_interval = 7200  # s
max_ping = 11.0  # s

# Get DATABASE_URL from environment variable
database_url = os.getenv('DATABASE_URL')

if not database_url:
    raise ValueError("DATABASE_URL environment variable is not set")

# Parse the DATABASE_URL
parsed_url = urlparse(database_url)

# Extract connection details from the parsed URL
psql_con = {
    "host": parsed_url.hostname,
    "db": parsed_url.path[1:],  # Remove the leading '/'
    "port": parsed_url.port,
    "user": parsed_url.username,
    "pass": parsed_url.password
}