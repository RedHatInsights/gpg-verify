#!/usr/bin/env python3

import base64
import json
import os
import re
from subprocess import PIPE, Popen

from graphqlclient import GraphQLClient

GITHUB_GPG_KEY = """
-----BEGIN PGP PUBLIC KEY BLOCK-----

xsBNBFmUaEEBCACzXTDt6ZnyaVtueZASBzgnAmK13q9Urgch+sKYeIhdymjuMQta
x15OklctmrZtqre5kwPUosG3/B2/ikuPYElcHgGPL4uL5Em6S5C/oozfkYzhwRrT
SQzvYjsE4I34To4UdE9KA97wrQjGoz2Bx72WDLyWwctD3DKQtYeHXswXXtXwKfjQ
7Fy4+Bf5IPh76dA8NJ6UtjjLIDlKqdxLW4atHe6xWFaJ+XdLUtsAroZcXBeWDCPa
buXCDscJcLJRKZVc62gOZXXtPfoHqvUPp3nuLA4YjH9bphbrMWMf810Wxz9JTd3v
yWgGqNY0zbBqeZoGv+TuExlRHT8ASGFS9SVDABEBAAHNNUdpdEh1YiAod2ViLWZs
b3cgY29tbWl0IHNpZ25pbmcpIDxub3JlcGx5QGdpdGh1Yi5jb20+wsBiBBMBCAAW
BQJZlGhBCRBK7hj4Ov3rIwIbAwIZAQAAmQEIACATWFmi2oxlBh3wAsySNCNV4IPf
DDMeh6j80WT7cgoX7V7xqJOxrfrqPEthQ3hgHIm7b5MPQlUr2q+UPL22t/I+ESF6
9b0QWLFSMJbMSk+BXkvSjH9q8jAO0986/pShPV5DU2sMxnx4LfLfHNhTzjXKokws
+8ptJ8uhMNIDXfXuzkZHIxoXk3rNcjDN5c5X+sK8UBRH092BIJWCOfaQt7v7wig5
4Ra28pM9GbHKXVNxmdLpCFyzvyMuCmINYYADsC848QQFFwnd4EQnupo6QvhEVx1O
j7wDwvuH5dCrLuLwtwXaQh0onG4583p0LGms2Mf5F+Ick6o/4peOlBoZz48=
=HXDP
-----END PGP PUBLIC KEY BLOCK-----
"""


def extract_user(line):
    if '"' not in line:
        return

    user_id = line.split('"')[1]
    match = re.search(pattern, user_id, re.IGNORECASE)
    if match:
        first_name = match.group(1)
        last_name = match.group(2)
        email = match.group(4)

        org_id = email.split("@")[0]

        if last_name:
            full_name = " ".join([first_name, last_name])
        else:
            full_name = first_name

        full_name = full_name.strip().lower()

        if org_id.lower() in user_dict:
            confirmed_users.add(org_id)
        elif full_name in user_dict:
            confirmed_users.add(user_dict[full_name])
        else:
            orphaned_users.add(user_id)


def get_github_actions_user():
    github_actions_user = {}
    github_actions_user["org_username"] = "Github"
    github_actions_user["full_name"] = "GitHub"
    github_actions_user["public_gpg_key"] = _read_local_github_gpg_key_file()
    return github_actions_user


def _read_local_github_gpg_key_file():
    return base64.b64encode(GITHUB_GPG_KEY.encode("ascii")).decode()


query = """{
  users: users_v1 {
    public_gpg_key
    org_username
    full_name: name
  }
}"""

DEFAULT_URL = "http://localhost:4000/graphql"

APP_INTERFACE_BASE_URL = os.getenv("APP_INTERFACE_BASE_URL")

QONTRACT_BASE_URL = os.getenv(
    "QONTRACT_BASE_URL",
    f"https://{APP_INTERFACE_BASE_URL}/graphql"
    if APP_INTERFACE_BASE_URL
    else DEFAULT_URL,
)

client = GraphQLClient(QONTRACT_BASE_URL)

if os.getenv("QONTRACT_TOKEN"):
    client.inject_token(os.getenv("QONTRACT_TOKEN"))
else:
    username = os.getenv("APP_INTERFACE_USERNAME")
    password = os.getenv("APP_INTERFACE_PASSWORD")
    basic_auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode(
        "ascii"
    )
    client.inject_token(f"Basic {basic_auth}")

users = json.loads(client.execute(query))["data"]["users"]

gpg_users = set()
user_dict = {}
big_bytes = b""
big_gpg_output = ""

github_actions_user = get_github_actions_user()
users.append(github_actions_user)

for user in (u for u in users if u["public_gpg_key"]):
    if user["org_username"] == "jmoshenk":
        continue
    if user["org_username"] == "rzaleski":
        continue

    proc = Popen("base64 -d", shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, _ = proc.communicate(user["public_gpg_key"].encode("ascii"))

    if proc.returncode > 0:
        print("Bad GPG key: %s" % user["org_username"])
        continue

    big_bytes = stdout

    proc = Popen(
        "gpg --no-default-keyring --keyring=$PWD/git.gpg --import -",
        shell=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )

    stdout, stderr = proc.communicate(big_bytes)

    if proc.returncode > 0:
        print("Bad time with key: %s" % user["org_username"])
        continue

    print("Encoded: %s" % stderr)
    big_gpg_output += stderr.decode("utf-8", errors="ignore")

    gpg_users.add(user["org_username"])
    user_dict[user["org_username"].lower()] = user["full_name"].lower().strip()
    user_dict[user["full_name"].lower().strip()] = user["org_username"].lower()

confirmed_users = set()
orphaned_users = set()
pattern = r"(\w+) (\w+ )?(\(.*\) )?<(.*)>"

for line in big_gpg_output.splitlines():
    extract_user(line)

missing_users = gpg_users - confirmed_users

print("Missing users:")
for missing_user in missing_users:
    print(missing_user)

print()

print("Orphaned users:")
for orphan in orphaned_users:
    print(orphan)
