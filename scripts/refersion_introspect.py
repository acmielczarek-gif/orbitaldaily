import os, json, requests

TOKEN = os.environ["REFERSION_API"]
ENDPOINT = "https://graphql.refersion.com"
HEADERS = {"X-Refersion-Key": TOKEN, "Content-Type": "application/json"}

introspection = """
{ __schema { queryType { fields { name description } } } }
"""

r = requests.post(ENDPOINT, json={"query": introspection}, headers=HEADERS)
print(json.dumps(r.json(), indent=2))
