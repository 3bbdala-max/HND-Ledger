// Validate a Genesis document using the exact CometBFT module checked out by CI.
package main

import (
	"fmt"
	"os"

	"github.com/cometbft/cometbft/types"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: cometbft_v040_genesis_validate <genesis.json>")
		os.Exit(2)
	}
	doc, err := types.GenesisDocFromFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if len(doc.Validators) != 4 {
		fmt.Fprintf(os.Stderr, "expected 4 validators, got %d\n", len(doc.Validators))
		os.Exit(1)
	}
	fmt.Printf("COMETBFT_V040_GENESIS_SCHEMA_OK chain_id=%s validators=%d initial_height=%d\n",
		doc.ChainID, len(doc.Validators), doc.InitialHeight)
}
