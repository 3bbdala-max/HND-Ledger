package ipc

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"sync/atomic"
	"time"
)

const (
	protocolVersion = "hnd-ipc/1"
	maxFrameBytes   = 1 << 20
)

type request struct {
	Protocol string          `json:"protocol"`
	ID       string          `json:"id"`
	Method   string          `json:"method"`
	Payload  json.RawMessage `json:"payload"`
}

type response struct {
	Protocol string          `json:"protocol"`
	ID       string          `json:"id"`
	OK       bool            `json:"ok"`
	Result   json.RawMessage `json:"result"`
	Error    *remoteError    `json:"error,omitempty"`
}

type remoteError struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
}

type RemoteError struct {
	Code      string
	Message   string
	Retryable bool
}

func (e *RemoteError) Error() string {
	return fmt.Sprintf("HND engine rejected %s: %s", e.Code, e.Message)
}

type Client struct {
	socketPath string
	nextID     atomic.Uint64
	timeout    time.Duration
}

func NewClient(socketPath string) (*Client, error) {
	if socketPath == "" {
		return nil, errors.New("HND_IPC_SOCKET must name a Unix-domain socket")
	}
	return &Client{socketPath: socketPath, timeout: 30 * time.Second}, nil
}

func writeFull(w io.Writer, data []byte) error {
	for len(data) > 0 {
		n, err := w.Write(data)
		if n > 0 {
			data = data[n:]
		}
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrShortWrite
		}
	}
	return nil
}

// Call opens one bounded request/response exchange. A fresh connection per
// call avoids cross-request framing ambiguity and makes reconnect behavior
// explicit. The Python peer remains the sole owner of ledger semantics.
func (c *Client) Call(ctx context.Context, method string, payload, result any) error {
	if method == "" || payload == nil || result == nil {
		return errors.New("method, payload, and result are required")
	}
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("encode %s payload: %w", method, err)
	}
	id := fmt.Sprintf("go-%d", c.nextID.Add(1))
	frame, err := json.Marshal(request{
		Protocol: protocolVersion,
		ID:       id,
		Method:   method,
		Payload:  payloadBytes,
	})
	if err != nil {
		return fmt.Errorf("encode %s envelope: %w", method, err)
	}
	if len(frame)+1 > maxFrameBytes {
		return fmt.Errorf("%s request exceeds IPC frame limit", method)
	}

	dialer := net.Dialer{Timeout: c.timeout}
	conn, err := dialer.DialContext(ctx, "unix", c.socketPath)
	if err != nil {
		return fmt.Errorf("connect to HND engine: %w", err)
	}
	defer conn.Close()
	deadline := time.Now().Add(c.timeout)
	if d, ok := ctx.Deadline(); ok && d.Before(deadline) {
		deadline = d
	}
	if err := conn.SetDeadline(deadline); err != nil {
		return fmt.Errorf("set IPC deadline: %w", err)
	}
	if err := writeFull(conn, append(frame, '\n')); err != nil {
		return fmt.Errorf("write %s request: %w", method, err)
	}
	if unixConn, ok := conn.(*net.UnixConn); ok {
		if err := unixConn.CloseWrite(); err != nil {
			return fmt.Errorf("finish %s request: %w", method, err)
		}
	}

	raw, err := io.ReadAll(io.LimitReader(conn, maxFrameBytes+1))
	if err != nil {
		return fmt.Errorf("read %s response: %w", method, err)
	}
	if len(raw) == 0 || len(raw) > maxFrameBytes {
		return fmt.Errorf("%s response is empty or exceeds IPC frame limit", method)
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	var reply response
	if err := decoder.Decode(&reply); err != nil {
		return fmt.Errorf("decode %s response: %w", method, err)
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("%s response contains trailing JSON data", method)
	}
	if reply.Protocol != protocolVersion || reply.ID != id {
		return fmt.Errorf("%s response protocol or request ID mismatch", method)
	}
	if !reply.OK {
		if reply.Error == nil || reply.Error.Code == "" {
			return fmt.Errorf("%s response has malformed remote error", method)
		}
		return &RemoteError{
			Code: reply.Error.Code, Message: reply.Error.Message,
			Retryable: reply.Error.Retryable,
		}
	}
	if len(reply.Result) == 0 {
		return fmt.Errorf("%s response omitted result", method)
	}
	resultDecoder := json.NewDecoder(bytes.NewReader(reply.Result))
	resultDecoder.DisallowUnknownFields()
	if err := resultDecoder.Decode(result); err != nil {
		return fmt.Errorf("decode %s result: %w", method, err)
	}
	if err := resultDecoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("%s result contains trailing JSON data", method)
	}
	return nil
}
