package ipc

import (
	"bufio"
	"context"
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
)

type testPayload struct {
	Value string `json:"value"`
}

func testServer(t *testing.T, handler func(map[string]any) map[string]any) string {
	t.Helper()
	socket := filepath.Join(t.TempDir(), "hnd.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil { t.Fatal(err) }
	t.Cleanup(func() { _ = listener.Close() })
	go func() {
		conn, err := listener.Accept()
		if err != nil { return }
		defer conn.Close()
		scanner := bufio.NewScanner(conn)
		scanner.Buffer(make([]byte, 1024), maxFrameBytes)
		if !scanner.Scan() { return }
		var req map[string]any
		if json.Unmarshal(scanner.Bytes(), &req) != nil { return }
		reply := handler(req)
		_ = json.NewEncoder(conn).Encode(reply)
	}()
	return socket
}

func TestCallCorrelatesRequestAndDecodesResult(t *testing.T) {
	socket := testServer(t, func(req map[string]any) map[string]any {
		return map[string]any{
			"protocol": req["protocol"], "id": req["id"], "ok": true,
			"result": map[string]any{"value": "committed"},
		}
	})
	client, err := NewClient(socket)
	if err != nil { t.Fatal(err) }
	var result testPayload
	if err := client.Call(context.Background(), "Info", map[string]any{"height": 7}, &result); err != nil {
		t.Fatal(err)
	}
	if result.Value != "committed" { t.Fatalf("unexpected result: %+v", result) }
}

func TestCallRejectsMismatchedRequestID(t *testing.T) {
	socket := testServer(t, func(req map[string]any) map[string]any {
		return map[string]any{
			"protocol": req["protocol"], "id": "wrong-id", "ok": true,
			"result": map[string]any{"value": "must-not-be-accepted"},
		}
	})
	client, err := NewClient(socket)
	if err != nil { t.Fatal(err) }
	var result testPayload
	if err := client.Call(context.Background(), "Info", map[string]any{}, &result); err == nil {
		t.Fatal("expected mismatched request ID to fail")
	}
}

func TestCallReturnsTypedRemoteError(t *testing.T) {
	socket := testServer(t, func(req map[string]any) map[string]any {
		return map[string]any{
			"protocol": req["protocol"], "id": req["id"], "ok": false,
			"error": map[string]any{"code": "INVALID_REQUEST", "message": "bad payload", "retryable": false},
		}
	})
	client, err := NewClient(socket)
	if err != nil { t.Fatal(err) }
	var result testPayload
	err = client.Call(context.Background(), "Info", map[string]any{}, &result)
	remote, ok := err.(*RemoteError)
	if !ok || remote.Code != "INVALID_REQUEST" || remote.Retryable {
		t.Fatalf("expected typed non-retryable remote error, got %#v", err)
	}
}
