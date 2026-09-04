#!/bin/bash
apt-get update && apt-get install -y curl gnupg2
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
ACCEPT_EULA=Y apt-get install -y msodbcsql18
pip install -r requirements.txt
gunicorn --bind=0.0.0.0 --timeout 600 app:app
