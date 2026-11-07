package ipc

import (
	"bufio"
	"bytes"
	"io"
	"context"
	"encoding/json"
	"net"
	"path/filepath"
	"testing"
	"time"
)


type partialWriter struct {
	buffer bytes.Buffer
	limit int
}

func (w *partialWriter) Write(data []byte) (int, error) {
	if len(data) > w.limit {
		data = data[:w.limit]
	}
	return w.buffer.Write(data)
}

func TestWriteFullRetriesPartialWrites(t *testing.T) {
	writer := &partialWriter{limit: 2}
	payload := []byte("bounded-ipc-frame")
	if err := writeFull(writer, payload); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(writer.buffer.Bytes(), payload) {
		t.Fatalf("partial write corrupted payload: %q", writer.buffer.Bytes())
	}
}

type zeroWriter struct{}

func (zeroWriter) Write([]byte) (int, error) { return 0, nil }

func TestWriteFullRejectsZeroProgress(t *testing.T) {
	if err := writeFull(zeroWriter{}, []byte("x")); err != io.ErrShortWrite {
		t.Fatalf("expected io.ErrShortWrite, got %v", err)
	}
}

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


func TestCallCancellationInterruptsBlockedResponseRead(t *testing.T) {
	socket := filepath.Join(t.TempDir(), "cancel.sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()

	requestReceived := make(chan struct{})
	serverDone := make(chan struct{})
	go func() {
		defer close(serverDone)
		conn, err := listener.Accept()
		if err != nil {
			return
		}
		defer conn.Close()
		scanner := bufio.NewScanner(conn)
		if !scanner.Scan() {
			return
		}
		close(requestReceived)
		// Deliberately withhold a response. The client must close the socket
		// when its context is canceled rather than waiting for its 30s timeout.
		_, _ = io.Copy(io.Discard, conn)
	}()

	client, err := NewClient(socket)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	callDone := make(chan error, 1)
	go func() {
		var result testPayload
		callDone <- client.Call(ctx, "Info", map[string]any{}, &result)
	}()

	select {
	case <-requestReceived:
	case <-time.After(2 * time.Second):
		cancel()
		t.Fatal("server did not receive IPC request")
	}
	cancel()

	select {
	case err := <-callDone:
		if err == nil {
			t.Fatal("expected canceled IPC call to fail")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("IPC call did not stop promptly after context cancellation")
	}

	select {
	case <-serverDone:
	case <-time.After(2 * time.Second):
		t.Fatal("server connection did not close after client cancellation")
	}
}
