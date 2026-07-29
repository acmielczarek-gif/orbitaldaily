import os, json, requests

TOKEN = os.environ["REFERSION_API"]
ENDPOINT = "https://graphql.refersion.com"
HEADERS = {"X-Refersion-Key": TOKEN, "Content-Type": "application/json"}

OFFERS_QUERY = """
query {
  offers(first: 20) {
    id
    type
    commission
    flat_rate_currency
    cookie_days
    commission_terms
    business_category
    unified_payments
    shop {
      name
      url
      currency
      shop_identifier
      terms_and_conditions
      privacy_policy
    }
    affiliates { id }
    conversions { id }
    clicks { sub_id }
  }
}
"""

PRODUCT_FEED_QUERY = """
query {
  product_feed(first: 20) {
    id
    merchant_id
    external_id
    name
    description
    tags
    price
    currency
    product_url
    rfsn_parameter
    platform_id
    sort
    limit
    before
    after
    offset
    first
    last
    merchant { id }
    vendor { id }
    variants { id }
    images { id }
  }
}
"""


def run_query(query):
    r = requests.post(ENDPOINT, json={"query": query}, headers=HEADERS)
    r.raise_for_status()
    return r.json()


def main():
    results = {
        "offers": run_query(OFFERS_QUERY),
        "product_feed": run_query(PRODUCT_FEED_QUERY),
    }

    pretty = json.dumps(results, indent=2)
    print(pretty)

    out_path = os.path.join(os.path.dirname(__file__), "refersion_products_raw.json")
    with open(out_path, "w") as f:
        f.write(pretty)


if __name__ == "__main__":
    main()
