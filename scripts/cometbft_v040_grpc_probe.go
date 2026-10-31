package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"time"

	abci "github.com/cometbft/cometbft/abci/types"
	cmtnet "github.com/cometbft/cometbft/libs/net"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	if len(os.Args) != 2 {
		panic("usage: grpc_probe <host:port>")
	}
	conn, err := grpc.NewClient(
		os.Args[1],
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithContextDialer(func(_ context.Context, addr string) (net.Conn, error) {
			return cmtnet.Connect(addr)
		}),
	)
	if err != nil {
		panic(fmt.Errorf("grpc.NewClient: %w", err))
	}
	defer conn.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	response, err := abci.NewABCIClient(conn).Echo(
		ctx,
		&abci.RequestEcho{Message: "HND Go gRPC probe"},
		grpc.WaitForReady(true),
	)
	if err != nil {
		panic(fmt.Errorf("ABCI Echo: %w", err))
	}
	if response.Message != "HND Go gRPC probe" {
		panic(fmt.Errorf("unexpected Echo response: %q", response.Message))
	}
	fmt.Println("HND_COMETBFT_GO_GRPC_PROBE_OK")
}
