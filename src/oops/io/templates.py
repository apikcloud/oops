# Copyright 2026 apik (https://apik.cloud).
# License AGPL-3.0-only (https://www.gnu.org/licenses/agpl-3.0.html)
#
# File: templates.py — src/oops/io/templates.py


from __future__ import annotations

COMPOSE_TEMPLATE = """\
services:
  odoo:
    image: {image}
    command: odoo{dev_flag}
    depends_on:
      - postgres
    ports:
      - "{port}:8069"
    environment:
      - HOST=postgres
      - USER=odoo
      - PASSWORD=odoo
{maildev_env}\
    volumes:
      - ./config:/etc/odoo:rw
      - .:/mnt/extra-addons:rw
      - {prefix}_odoo:/var/lib/odoo
  postgres:
    image: postgres:16.0
    environment:
      - POSTGRES_DB=postgres
      - POSTGRES_PASSWORD=odoo
      - POSTGRES_USER=odoo
      - PGDATA=/var/lib/postgresql/data/pgdata
    volumes:
      - {prefix}_postgres:/var/lib/postgresql/data/pgdata
{maildev_service}\
{sftp_service}\
volumes:
  {prefix}_odoo:
  {prefix}_postgres:
"""

MAILDEV_ENV = """\
      - SMTP_HOST=maildev
      - SMTP_PORT=1025
"""

MAILDEV_SERVICE = """\
  maildev:
    image: maildev/maildev
    ports:
      - "1080:1080"
    depends_on:
      - odoo
    environment:
      - TZ=Europe/Paris
"""

SFTP_SERVICE = """\
  sftp:
    image: atmoz/sftp
    volumes:
      - ./sftp:/home/user/upload
    ports:
      - "2222:22"
    command: user:password:1001
"""

ODOO_CONF = """\
[options]
addons_path = /mnt/extra-addons
limit_memory_soft = 1077721600
limit_memory_hard = 3355443200
limit_request = 8192
limit_time_cpu = 3200
limit_time_real = 3200
max_cron_threads = 0
workers = 0
db_host = postgres
db_port = 5432
db_user = odoo
db_password = odoo
"""

CONFIG_STARTER = """\
# oops configuration — see https://apikcloud.github.io/oops/latest/config/
version: 1

manifest:
  odoo_version: "19.0"
"""
