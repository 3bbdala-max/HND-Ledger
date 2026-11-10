// cometbft-v040-config-schema-dump emits a deterministic, source-derived
// inventory of exported CometBFT Config fields and DefaultConfig values.
// Run from the pinned CometBFT source module:
//   go run /path/to/HND-Ledger/scripts/cometbft_v040_config_schema_dump.go
//
// This is an inventory aid, not a TOML decoder or consensus-field classifier.
// The rendered TOML template, custom decoding, validation, env/CLI overrides,
// and operational-vs-consensus scope still require independent reconciliation.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"strings"

	cfg "github.com/cometbft/cometbft/config"
)

type Field struct {
	GoPath       string          `json:"go_path"`
	GoName       string          `json:"go_name"`
	GoType       string          `json:"go_type"`
	Mapstructure string          `json:"mapstructure"`
	Anonymous    bool            `json:"anonymous,omitempty"`
	DefaultJSON json.RawMessage `json:"default_json,omitempty"`
}

type Inventory struct {
	SourceCommit string  `json:"source_commit"`
	RootType     string  `json:"root_type"`
	Fields       []Field `json:"fields"`
}

func defaultJSON(v reflect.Value) json.RawMessage {
	if !v.IsValid() || !v.CanInterface() {
		return nil
	}
	b, err := json.Marshal(v.Interface())
	if err != nil {
		return json.RawMessage(`"UNSERIALIZABLE"`)
	}
	return b
}

func walk(t reflect.Type, v reflect.Value, prefix string, out *[]Field) {
	for i := 0; i < t.NumField(); i++ {
		sf := t.Field(i)
		if sf.PkgPath != "" { // unexported implementation detail, not public config
			continue
		}
		fv := v.Field(i)
		path := sf.Name
		if prefix != "" {
			path = prefix + "." + sf.Name
		}
		tag := strings.Split(sf.Tag.Get("mapstructure"), ",")[0]
		entry := Field{
			GoPath: path, GoName: sf.Name, GoType: sf.Type.String(),
			Mapstructure: tag, Anonymous: sf.Anonymous,
		}
		if sf.Type.Kind() != reflect.Struct && sf.Type.Kind() != reflect.Pointer {
			entry.DefaultJSON = defaultJSON(fv)
		} else if sf.Type.Kind() == reflect.Pointer {
			entry.DefaultJSON = defaultJSON(fv)
		}
		*out = append(*out, entry)

		switch sf.Type.Kind() {
		case reflect.Struct:
			walk(sf.Type, fv, path, out)
		case reflect.Pointer:
			if !fv.IsNil() && fv.Elem().Kind() == reflect.Struct {
				walk(fv.Type().Elem(), fv.Elem(), path, out)
			}
		}
	}
}

func main() {
	defaults := cfg.DefaultConfig()
	t := reflect.TypeOf(*defaults)
	v := reflect.ValueOf(*defaults)
	inventory := Inventory{
		SourceCommit: "0880b4d378f347ab16e54ec677ff50d803f37d62",
		RootType: t.String(),
		Fields: make([]Field, 0, 160),
	}
	walk(t, v, "", &inventory.Fields)
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(inventory); err != nil {
		fmt.Fprintln(os.Stderr, "schema inventory encode failed:", err)
		os.Exit(1)
	}
}
