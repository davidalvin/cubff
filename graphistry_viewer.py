import pandas as pd
import graphistry
import argparse
import math
import getpass

# CLI setup
parser = argparse.ArgumentParser(description="Visualize a CSV graph with Graphistry.")
parser.add_argument("input_csv", help="Path to CSV file with source_bin, target_bin, weight")
parser.add_argument("--log-weight", action="store_true", help="Apply natural log to edge weights before visualization")

args = parser.parse_args()

# Prompt for credentials securely
key_id = input("Enter your Graphistry personal_key_id: ")
key_secret = input("Enter your Graphistry personal_key_secret: ")

# Register with Graphistry using API keys
graphistry.register(
    api=3,
    protocol="https",
    server="hub.graphistry.com",
    personal_key_id=key_id,
    personal_key_secret=key_secret
)

# Load the CSV
df = pd.read_csv(args.input_csv)

# Optionally log-scale the weights
if args.log_weight:
    df["weight"] = df["weight"].apply(lambda w: math.log(w) if w > 0 else 0)

# Bind and visualize
g = (
    graphistry
    .edges(df)
    .bind(source="source_bin", destination="target_bin", edge_weight="weight")
    .settings(url_params={
        "edgeWeightAttr": "weight",
        "edgeSize": 0.6,        # global edge size multiplier
        "edgeMinSize": 0.5,
        "edgeMaxSize": 5,
        "colorBy": "weight",
        "colorAggregation": "mean"
    })
)


g.plot()
