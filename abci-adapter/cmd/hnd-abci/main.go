package main

import (
	"context"
	"fmt"
	"net"
	"net/url"
	"strconv"
	"strings"
	"os"
	"os/signal"
	"syscall"

	"github.com/cometbft/cometbft/abci/server"

	"github.com/3bbdala-max/HND-Ledger/abci-adapter/internal/abciapp"
	"github.com/3bbdala-max/HND-Ledger/abci-adapter/internal/ipc"
)

func validateListenAddress(address string) error {
	parsed, err := url.Parse(address)
	if err != nil {
		return fmt.Errorf("invalid HND_ABCI_LISTEN URL: %w", err)
	}
	if parsed.Scheme != "tcp" || parsed.Opaque != "" || parsed.User != nil ||
		parsed.Path != "" || parsed.RawQuery != "" || parsed.Fragment != "" {
		return fmt.Errorf("HND_ABCI_LISTEN must be a loopback tcp://host:port address")
	}
	host, port, err := net.SplitHostPort(parsed.Host)
	if err != nil {
		return fmt.Errorf("HND_ABCI_LISTEN must include a valid host and port: %w", err)
	}
	if !strings.EqualFold(host, "localhost") {
		ip := net.ParseIP(host)
		if ip == nil || !ip.IsLoopback() {
			return fmt.Errorf("HND_ABCI_LISTEN must bind to loopback; public ABCI listeners are refused")
		}
	}
	portNumber, err := strconv.Atoi(port)
	if err != nil || portNumber < 1 || portNumber > 65535 {
		return fmt.Errorf("HND_ABCI_LISTEN port must be between 1 and 65535")
	}
	return nil
}

func main() {
	listenAddress := os.Getenv("HND_ABCI_LISTEN")
	socketPath := os.Getenv("HND_IPC_SOCKET")
	if listenAddress == "" || socketPath == "" {
		fmt.Fprintln(os.Stderr, "HND_ABCI_LISTEN and HND_IPC_SOCKET are required")
		os.Exit(2)
	}
	if err := validateListenAddress(listenAddress); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	client, err := ipc.NewClient(socketPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	app := abciapp.New(client)
	srv := server.NewSocketServer(listenAddress, app)
	if err := srv.Start(); err != nil {
		fmt.Fprintln(os.Stderr, "start ABCI socket server:", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	select {
	case <-ctx.Done():
		if err := srv.Stop(); err != nil {
			fmt.Fprintln(os.Stderr, "stop ABCI socket server:", err)
		}
	case <-srv.Quit():
	}
}
