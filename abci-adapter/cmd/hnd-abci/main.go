package main

import (
	"context"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"github.com/cometbft/cometbft/abci/server"

	"github.com/3bbdala-max/HND-Ledger/abci-adapter/internal/abciapp"
	"github.com/3bbdala-max/HND-Ledger/abci-adapter/internal/ipc"
)

func main() {
	listenAddress := os.Getenv("HND_ABCI_LISTEN")
	socketPath := os.Getenv("HND_IPC_SOCKET")
	if listenAddress == "" || socketPath == "" {
		fmt.Fprintln(os.Stderr, "HND_ABCI_LISTEN and HND_IPC_SOCKET are required")
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
