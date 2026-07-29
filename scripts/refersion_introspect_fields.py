import os, json, requests, sys

TOKEN = os.environ["REFERSION_API"]
ENDPOINT = "https://graphql.refersion.com"
HEADERS = {"X-Refersion-Key": TOKEN, "Content-Type": "application/json"}

query = """
{
  __schema {
    types {
      name
      kind
      fields {
        name
        type { name kind ofType { name kind ofType { name kind } } }
      }
    }
  }
}
"""

r = requests.post(ENDPOINT, json={"query": query}, headers=HEADERS)
data = r.json()

types = data.get("data", {}).get("__schema", {}).get("types", [])
wanted = set(sys.argv[1:]) or {
    "Shop", "Affiliate", "Conversion", "Click",
    "Merchant", "Platform", "Variant", "Image",
}
for t in types:
    if t["name"] in wanted:
        print(json.dumps(t, indent=2))
