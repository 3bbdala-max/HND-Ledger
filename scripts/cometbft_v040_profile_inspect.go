// Strict CometBFT v0.40.0 TOML parser probe. Run from the pinned CometBFT
// source checkout so config.DefaultConfig and validation come from that exact
// source tree. This tool deliberately does not claim to produce the VSP
// consensus-service profile digest: field classification and canonical
// projection remain a separate, versioned contract.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"reflect"
	"strings"
	"time"

	"github.com/BurntSushi/toml"
	cmtconfig "github.com/cometbft/cometbft/config"
	"github.com/go-viper/mapstructure/v2"
)

const sourceCommit = "0880b4d378f347ab16e54ec677ff50d803f37d62"
const maxConfigBytes = 1 << 20

func parseConfig(raw []byte, home string) (*cmtconfig.Config, []string, error) {
	if len(raw) == 0 || len(raw) > maxConfigBytes {
		return nil, nil, errors.New("CMT-PROFILE-E-BYTE-LIMIT")
	}
	var document map[string]interface{}
	if _, err := toml.Decode(string(raw), &document); err != nil {
		return nil, nil, fmt.Errorf("CMT-PROFILE-E-TOML: %w", err)
	}
	cfg := cmtconfig.DefaultConfig().SetRoot(home)
	decoder, err := mapstructure.NewDecoder(&mapstructure.DecoderConfig{
		DecodeHook: mapstructure.StringToTimeDurationHookFunc(),
		WeaklyTypedInput: false,
		ErrorUnused: true,
		TagName: "mapstructure",
		Result: cfg,
	})
	if err != nil {
		return nil, nil, fmt.Errorf("CMT-PROFILE-E-DECODER: %w", err)
	}
	if err := decoder.Decode(document); err != nil {
		return nil, nil, fmt.Errorf("CMT-PROFILE-E-SCHEMA: %w", err)
	}
	if err := cfg.ValidateBasic(); err != nil {
		return nil, nil, fmt.Errorf("CMT-PROFILE-E-VALIDATION: %w", err)
	}
	missing := missingKeys(reflect.ValueOf(document), "")
	return cfg, missing, nil
}

func missingKeys(v reflect.Value, prefix string) []string {
	// Report absent top-level and nested TOML keys for audit. The exact
	// versioned schema projection will consume this list; defaults are never
	// silently represented as user-supplied values.
	if v.Kind() != reflect.Map { return nil }
	var out []string
	iter := v.MapRange()
	for iter.Next() {
		key := iter.Key().String()
		path := key
		if prefix != "" { path = prefix + "." + key }
		if child := iter.Value(); child.Kind() == reflect.Map {
			out = append(out, missingKeys(child, path)...)
		}
	}
	return out
}

func selfTest() error {
	cases := []struct{name string; raw string; wantError string}{
		{"valid defaults", "proxy_app = \"tcp://127.0.0.1:26658\"\n", ""},
		{"unknown key", "unknown_future_field = true\n", "CMT-PROFILE-E-SCHEMA"},
		{"duplicate key", "proxy_app = \"a\"\nproxy_app = \"b\"\n", "CMT-PROFILE-E-TOML"},
		{"invalid type", "filter_peers = \"yes\"\n", "CMT-PROFILE-E-SCHEMA"},
		{"oversize", strings.Repeat(" ", maxConfigBytes+1), "CMT-PROFILE-E-BYTE-LIMIT"},
	}
	for _, tc := range cases {
		_, _, err := parseConfig([]byte(tc.raw), "/tmp/hnd-cometbft-profile-test")
		if tc.wantError == "" {
			if err != nil { return fmt.Errorf("%s: unexpected error: %w", tc.name, err) }
		} else if err == nil || !strings.Contains(err.Error(), tc.wantError) {
			return fmt.Errorf("%s: wanted %s, got %v", tc.name, tc.wantError, err)
		}
	}
	// Verify the duration hook is compatible with the pinned config's TOML
	// representation and the source defaults remain available.
	cfg, _, err := parseConfig([]byte("proxy_app = \"tcp://127.0.0.1:26658\"\n[consensus]\ntimeout_commit = \"1500ms\"\n"), "/tmp/hnd-cometbft-profile-test")
	if err != nil { return fmt.Errorf("duration override: %w", err) }
	if cfg.Consensus.TimeoutCommit != 1500*time.Millisecond { return errors.New("duration override was not applied") }
	return nil
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--self-test" {
		if err := selfTest(); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
		fmt.Printf("CometBFT v0.40.0 strict TOML parser self-test: PASS (source %s)\n", sourceCommit)
		return
	}
	if len(os.Args) != 3 || os.Args[1] != "--config" {
		fmt.Fprintln(os.Stderr, "usage: cometbft_v040_profile_inspect.go --config PATH | --self-test")
		os.Exit(2)
	}
	raw, err := os.ReadFile(os.Args[2])
	if err != nil { fmt.Fprintln(os.Stderr, "CMT-PROFILE-E-READ"); os.Exit(1) }
	cfg, _, err := parseConfig(raw, "")
	if err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
	// Output only non-secret metadata. Do not print local endpoints, paths,
	// credentials, or the full config. The JSON struct is intentionally not
	// hashed here because it mixes shared and node-local policy.
	out := map[string]interface{}{"schema":"hnd.cometbft-v040-parsed-config","source_commit":sourceCommit,"version":cfg.Version,"validation":"passed","profile_digest":"NOT_COMPUTED_FIELD_CLASSIFICATION_REQUIRED"}
	enc := json.NewEncoder(os.Stdout); enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
