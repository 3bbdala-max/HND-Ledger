// cometbft-v040-config-schema-dump renders the pinned Config.DefaultConfig()
// through CometBFT's own config.toml template, parses that TOML with the
// dependency pinned by the same CometBFT module, and reconciles every emitted
// TOML key against the Config struct's mapstructure tags.
//
// Run from the exact CometBFT source module:
//   go run /path/to/HND-Ledger/scripts/cometbft_v040_config_schema_dump.go
//
// This produces a source inventory (TOML type + rendered default + Go source
// field path). It deliberately does NOT assign shared/node-local/software
// consensus scopes. Those are protocol-policy decisions and need a separately
// reviewed, exhaustive scope manifest before a ProfileSchema is production
// complete.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"reflect"
	"sort"
	"strings"

	"github.com/BurntSushi/toml"
	cfg "github.com/cometbft/cometbft/config"
)

const sourceCommit = "0880b4d378f347ab16e54ec677ff50d803f37d62"

type ItemField struct {
	Name     string          `json:"name"`
	GoPath   string          `json:"go_path"`
	GoType   string          `json:"go_type"`
	Required bool            `json:"required"`
	Default  json.RawMessage `json:"default,omitempty"`
}

type Field struct {
	Path        string          `json:"path"`
	GoPath      string          `json:"go_path"`
	GoType      string          `json:"go_type"`
	TOMLType    string          `json:"toml_type"`
	Default     json.RawMessage `json:"default"`
	HasDefault  bool            `json:"has_default"`
	ItemType    string          `json:"item_type,omitempty"`
	ItemFields  []ItemField     `json:"item_fields,omitempty"`
}

type ExcludedField struct {
	Path   string `json:"path"`
	GoPath string `json:"go_path"`
	GoType string `json:"go_type"`
	Reason string `json:"reason"`
}

type Inventory struct {
	SchemaVersion        int             `json:"schema_version"`
	SourceCommit         string          `json:"source_commit"`
	RootType             string          `json:"root_type"`
	RenderedTemplateSHA  string          `json:"rendered_template_sha256"`
	TemplateComplete     bool            `json:"template_complete"`
	Fields               []Field         `json:"fields"`
	Tables               []string        `json:"tables"`
	ExcludedSourceFields []ExcludedField `json:"excluded_source_fields"`
}

func isDuration(t reflect.Type) bool {
	return t.PkgPath() == "time" && t.Name() == "Duration"
}

func tomlType(v any) (string, error) {
	switch v.(type) {
	case string:
		return "string", nil
	case bool:
		return "boolean", nil
	case int64, int:
		return "integer", nil
	case float64:
		return "float", nil
	case []any:
		return "array", nil
	case map[string]any:
		return "table", nil
	default:
		value := reflect.ValueOf(v)
		switch value.Kind() {
		case reflect.Slice, reflect.Array:
			return "array", nil
		case reflect.Map:
			return "table", nil
		default:
			return "", fmt.Errorf("unsupported TOML value type %T", v)
		}
	}
}

func joinPath(prefix, name string) string {
	if prefix == "" {
		return name
	}
	return prefix + "." + name
}

func splitMapstructure(tag string) (name string, squash bool, ignored bool) {
	parts := strings.Split(tag, ",")
	name = parts[0]
	for _, option := range parts[1:] {
		switch option {
		case "squash":
			squash = true
		}
	}
	if name == "-" {
		ignored = true
	}
	return
}

func lookup(document map[string]any, dotted string) (any, bool) {
	var current any = document
	for _, part := range strings.Split(dotted, ".") {
		m, ok := current.(map[string]any)
		if !ok {
			m2, ok2 := current.(map[string]interface{})
			if !ok2 {
				return nil, false
			}
			m = m2
		}
		value, exists := m[part]
		if !exists {
			return nil, false
		}
		current = value
	}
	return current, true
}

func flattenTOML(value map[string]any, prefix string, leaves map[string]any, tables *[]string) {
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	if prefix != "" {
		*tables = append(*tables, prefix)
	}
	for _, key := range keys {
		path := joinPath(prefix, key)
		switch child := value[key].(type) {
		case map[string]any:
			flattenTOML(child, path, leaves, tables)
		default:
			leaves[path] = child
		}
	}
}

func primitiveGoType(t reflect.Type) string {
	if t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if isDuration(t) {
		return "time.Duration"
	}
	return t.String()
}

func arrayItemFields(t reflect.Type, prefix string) ([]ItemField, error) {
	if t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil, fmt.Errorf("array table %s has non-struct item %s", prefix, t)
	}
	items := make([]ItemField, 0, t.NumField())
	for i := 0; i < t.NumField(); i++ {
		sf := t.Field(i)
		if sf.PkgPath != "" {
			continue
		}
		name, _, ignored := splitMapstructure(sf.Tag.Get("mapstructure"))
		if ignored || name == "" {
			continue
		}
		required := true
		var defaultValue json.RawMessage
		// CometBFT's ToTOMLInlineString deliberately omits false-valued
		// bootstrap-peer flags. Missing keys therefore normalize to false.
		if prefix == "p2p.libp2p.bootstrap_peers" &&
			(name == "private" || name == "persistent" || name == "unconditional") {
			required = false
			defaultValue = json.RawMessage("false")
		}
		items = append(items, ItemField{
			Name: name,
			GoPath: prefix + "[]." + sf.Name,
			GoType: primitiveGoType(sf.Type),
			Required: required,
			Default: defaultValue,
		})
	}
	sort.Slice(items, func(i, j int) bool { return items[i].Name < items[j].Name })
	return items, nil
}

func walkStruct(
	t reflect.Type,
	v reflect.Value,
	prefix string,
	document map[string]any,
	fields map[string]Field,
	excluded *[]ExcludedField,
) error {
	for t.Kind() == reflect.Pointer {
		if v.IsNil() {
			return fmt.Errorf("nil config pointer at %s", prefix)
		}
		t = t.Elem()
		v = v.Elem()
	}
	if t.Kind() != reflect.Struct {
		return fmt.Errorf("expected struct at %s, got %s", prefix, t)
	}

	for i := 0; i < t.NumField(); i++ {
		sf := t.Field(i)
		if sf.PkgPath != "" {
			continue // unexported implementation detail
		}
		fv := v.Field(i)
		name, squash, ignored := splitMapstructure(sf.Tag.Get("mapstructure"))
		goPath := joinPath(prefix, sf.Name)

		if ignored {
			continue
		}
		if sf.Anonymous && squash {
			if err := walkStruct(sf.Type, fv, prefix, document, fields, excluded); err != nil {
				return err
			}
			continue
		}
		if name == "" {
			*excluded = append(*excluded, ExcludedField{
				Path: goPath, GoPath: goPath, GoType: sf.Type.String(),
				Reason: "no mapstructure key",
			})
			continue
		}

		path := joinPath(prefix, name)
		if name == "home" {
			*excluded = append(*excluded, ExcludedField{
				Path: path, GoPath: goPath, GoType: sf.Type.String(),
				Reason: "root directory is supplied by the CLI/environment, not config.toml",
			})
			continue
		}

		fieldType := sf.Type
		if fieldType.Kind() == reflect.Pointer {
			fieldType = fieldType.Elem()
		}

		// Nested structs map to TOML tables. Duration is an int64 alias but
		// is rendered and parsed as a TOML string, so it is handled as a leaf.
		if fieldType.Kind() == reflect.Struct && !isDuration(fieldType) {
			tableValue, ok := lookup(document, path)
			_, isTable := tableValue.(map[string]any)
			if !ok || !isTable {
				*excluded = append(*excluded, ExcludedField{
					Path: path, GoPath: goPath, GoType: sf.Type.String(),
					Reason: "source struct is not rendered as a TOML table",
				})
				continue
			}
			if err := walkStruct(sf.Type, fv, path, document, fields, excluded); err != nil {
				return err
			}
			continue
		}

		defaultValue, ok := lookup(document, path)
		if !ok {
			// CometBFT's TOML template omits empty arrays of tables. Preserve
			// their source-defined field and empty default in the schema so a
			// profile can still supply entries (for example bootstrap_peers).
			element := fieldType
			if element.Kind() == reflect.Slice {
				element = element.Elem()
				if element.Kind() == reflect.Pointer {
					element = element.Elem()
				}
			}
			if fieldType.Kind() == reflect.Slice && element.Kind() == reflect.Struct && fv.Len() == 0 {
				defaultValue = []any{}
				ok = true
			} else {
				*excluded = append(*excluded, ExcludedField{
					Path: path, GoPath: goPath, GoType: sf.Type.String(),
					Reason: "source field is not emitted by the pinned default TOML template",
				})
				continue
			}
		}

		kind, err := tomlType(defaultValue)
		if err != nil {
			return fmt.Errorf("%s (%s): %w", path, sf.Type, err)
		}
		entry := Field{
			Path: path, GoPath: goPath, GoType: primitiveGoType(sf.Type),
			TOMLType: kind, HasDefault: true,
		}
		entry.Default, err = json.Marshal(defaultValue)
		if err != nil {
			return fmt.Errorf("%s default cannot be serialized: %w", path, err)
		}

		if fieldType.Kind() == reflect.Slice {
			element := fieldType.Elem()
			if element.Kind() == reflect.Pointer {
				element = element.Elem()
			}
			if element.Kind() == reflect.Struct {
				entry.ItemType = "table"
				entry.ItemFields, err = arrayItemFields(element, path)
				if err != nil {
					return err
				}
				items := reflect.ValueOf(defaultValue)
				for index := 0; index < items.Len(); index++ {
					item := items.Index(index).Interface()
					itemMap, ok := item.(map[string]any)
					if !ok {
						if m, ok := item.(map[string]interface{}); ok {
							itemMap = m
						} else {
							return fmt.Errorf("%s default array item %d is not a table", path, index)
						}
					}
					allowed := make(map[string]bool, len(entry.ItemFields))
					for _, child := range entry.ItemFields {
						allowed[child.Name] = true
					}
					for key := range itemMap {
						if !allowed[key] {
							return fmt.Errorf("%s default array item has unknown key %q", path, key)
						}
					}
					for _, child := range entry.ItemFields {
						if child.Required {
							if _, exists := itemMap[child.Name]; !exists {
								return fmt.Errorf("%s default array item missing %q", path, child.Name)
							}
						}
					}
				}
			} else {
				entry.ItemType = primitiveGoType(element)
			}
		}
		fields[path] = entry
	}
	return nil
}

func main() {
	defaults := cfg.DefaultConfig()
	tmp, err := os.CreateTemp("", "cometbft-v040-default-config-*.toml")
	if err != nil {
		fmt.Fprintln(os.Stderr, "cannot create temporary config:", err)
		os.Exit(1)
	}
	tmpPath := tmp.Name()
	if err := tmp.Close(); err != nil {
		fmt.Fprintln(os.Stderr, "cannot close temporary config:", err)
		os.Exit(1)
	}
	defer os.Remove(tmpPath)

	cfg.WriteConfigFile(tmpPath, defaults)
	rendered, err := os.ReadFile(tmpPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "cannot read rendered config:", err)
		os.Exit(1)
	}
	document := map[string]any{}
	if _, err := toml.Decode(string(rendered), &document); err != nil {
		fmt.Fprintln(os.Stderr, "CometBFT default TOML failed to parse:", err)
		os.Exit(1)
	}

	leaves := make(map[string]any)
	var tables []string
	flattenTOML(document, "", leaves, &tables)

	fields := make(map[string]Field, len(leaves))
	var excluded []ExcludedField
	if err := walkStruct(
		reflect.TypeOf(*defaults), reflect.ValueOf(*defaults), "",
		document, fields, &excluded,
	); err != nil {
		fmt.Fprintln(os.Stderr, "source/TOML reconciliation failed:", err)
		os.Exit(1)
	}

	if len(fields) < len(leaves) {
		fmt.Fprintf(os.Stderr, "source/TOML field count mismatch: source=%d TOML=%d\n", len(fields), len(leaves))
		os.Exit(1)
	}
	for path := range leaves {
		if _, exists := fields[path]; !exists {
			fmt.Fprintf(os.Stderr, "TOML field is absent from Config mapstructure inventory: %s\n", path)
			os.Exit(1)
		}
	}
	for path, field := range fields {
		if _, exists := leaves[path]; !exists {
			// Empty array-of-table defaults are intentionally omitted by
			// CometBFT's template but remain valid source-defined TOML fields.
			if field.TOMLType == "array" && field.ItemType == "table" && string(field.Default) == "[]" {
				continue
			}
			fmt.Fprintf(os.Stderr, "source field was not parsed from TOML: %s\n", path)
			os.Exit(1)
		}
	}

	orderedFields := make([]Field, 0, len(fields))
	for _, field := range fields {
		orderedFields = append(orderedFields, field)
	}
	sort.Slice(orderedFields, func(i, j int) bool {
		return orderedFields[i].Path < orderedFields[j].Path
	})
	sort.Strings(tables)
	sort.Slice(excluded, func(i, j int) bool {
		if excluded[i].Path == excluded[j].Path {
			return excluded[i].GoPath < excluded[j].GoPath
		}
		return excluded[i].Path < excluded[j].Path
	})

	templateDigest := sha256.Sum256(rendered)
	inventory := Inventory{
		SchemaVersion: 1,
		SourceCommit: sourceCommit,
		RootType: reflect.TypeOf(*defaults).String(),
		RenderedTemplateSHA: hex.EncodeToString(templateDigest[:]),
		TemplateComplete: true,
		Fields: orderedFields,
		Tables: tables,
		ExcludedSourceFields: excluded,
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(inventory); err != nil {
		fmt.Fprintln(os.Stderr, "schema inventory encode failed:", err)
		os.Exit(1)
	}
}
