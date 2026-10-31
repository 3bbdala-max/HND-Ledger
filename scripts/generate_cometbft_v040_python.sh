#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COMET_TAG="v0.40.0"
GOGO_TAG="v1.7.2"
COMET_DIR="$TMP/cometbft"
GOGO_DIR="$TMP/gogoproto"
OUT="$ROOT/hnd_v02/_cometbft_v040"

git clone --quiet --depth 1 --branch "$COMET_TAG" https://github.com/cometbft/cometbft.git "$COMET_DIR"
git clone --quiet --depth 1 --branch "$GOGO_TAG" https://github.com/cosmos/gogoproto.git "$GOGO_DIR"

rm -rf "$OUT"
mkdir -p "$OUT"
PROTO_ROOT="$COMET_DIR/proto"
GOOGLE_PROTO_ROOT="$(python -c 'import pathlib, grpc_tools; print(pathlib.Path(grpc_tools.__file__).parent / "_proto")')"

mapfile -t PROTOS < <(find "$PROTO_ROOT/tendermint" -type f -name '*.proto' | sort)

python -m grpc_tools.protoc \
  -I "$PROTO_ROOT" \
  -I "$GOGO_DIR" \
  -I "$GOOGLE_PROTO_ROOT" \
  --python_out="$OUT" \
  --grpc_python_out="$OUT" \
  "${PROTOS[@]}"

find "$OUT" -type d -exec touch "{}/__init__.py" \;

echo "Generated CometBFT $COMET_TAG ABCI Python bindings."
echo "CometBFT tag commit: $(git -C "$COMET_DIR" rev-parse HEAD)"
echo "gogoproto tag commit: $(git -C "$GOGO_DIR" rev-parse HEAD)"
