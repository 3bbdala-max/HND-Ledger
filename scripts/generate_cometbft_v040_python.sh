#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

COMET_TAG="v0.40.0"
COMET_COMMIT="0880b4d378f347ab16e54ec677ff50d803f37d62"
GOGO_TAG="v1.7.2"
GOGO_COMMIT="cf5213e4dcbf1fea203185c0af00840e566790d9"
COMET_DIR="$TMP/cometbft"
GOGO_DIR="$TMP/gogoproto"
OUT="$ROOT/hnd_v02/_cometbft_v040"

git init --quiet "$COMET_DIR"
git -C "$COMET_DIR" remote add origin https://github.com/cometbft/cometbft.git
git -C "$COMET_DIR" fetch --quiet --depth 1 origin "$COMET_COMMIT"
git -C "$COMET_DIR" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$COMET_DIR" rev-parse HEAD)" = "$COMET_COMMIT"

git init --quiet "$GOGO_DIR"
git -C "$GOGO_DIR" remote add origin https://github.com/cosmos/gogoproto.git
git -C "$GOGO_DIR" fetch --quiet --depth 1 origin "$GOGO_COMMIT"
git -C "$GOGO_DIR" checkout --quiet --detach FETCH_HEAD
test "$(git -C "$GOGO_DIR" rev-parse HEAD)" = "$GOGO_COMMIT"

rm -rf "$OUT"
mkdir -p "$OUT"
PROTO_ROOT="$COMET_DIR/proto"
GOOGLE_PROTO_ROOT="$(python -c 'import pathlib, grpc_tools; print(pathlib.Path(grpc_tools.__file__).parent / "_proto")')"

mapfile -t PROTOS < <(find "$PROTO_ROOT/tendermint" -type f -name '*.proto' | sort)
PROTOS+=("$GOGO_DIR/gogoproto/gogo.proto")

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
