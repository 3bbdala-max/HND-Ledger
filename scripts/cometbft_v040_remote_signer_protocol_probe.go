// Disposable protocol-conformance smoke test for CometBFT v0.40.0 remote privval.
// Run from the pinned CometBFT source module with: go run <this-file>.
// The Unix socket is local and unencrypted; this probe validates protocol/API
// compatibility only, not authenticated transport or cross-process isolation.
package main

import (
	"fmt"
	"net"
	"os"
	"path/filepath"

	"github.com/cometbft/cometbft/crypto/tmhash"
	"github.com/cometbft/cometbft/libs/log"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmttypes "github.com/cometbft/cometbft/types"
	cmttime "github.com/cometbft/cometbft/types/time"
)

const chainID = "hnd-cometbft-v040-remote-signer-probe"

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "HND_REMOTE_SIGNER_PROBE_FAILED: "+format+"\n", args...)
	os.Exit(1)
}

func testBlockID(label string) cmttypes.BlockID {
	return cmttypes.BlockID{
		Hash: tmhash.Sum([]byte("hnd-remote-signer-block-" + label)),
		PartSetHeader: cmttypes.PartSetHeader{
			Total: 1,
			Hash:  tmhash.Sum([]byte("hnd-remote-signer-parts-" + label)),
		},
	}
}

func main() {
	root, err := os.MkdirTemp("", "hnd-remote-signer-v040-")
	if err != nil {
		fail("create temporary directory: %v", err)
	}
	defer os.RemoveAll(root)

	socketPath := filepath.Join(root, "privval.sock")
	rawListener, err := net.Listen("unix", socketPath)
	if err != nil {
		fail("listen on temporary Unix socket: %v", err)
	}
	defer rawListener.Close()
	if err := os.Chmod(socketPath, 0o600); err != nil {
		fail("restrict socket permissions: %v", err)
	}

	logger := log.NewNopLogger()
	nodeListener := privval.NewSignerListenerEndpoint(logger, privval.NewUnixListener(rawListener))
	client, err := privval.NewSignerClient(nodeListener, chainID)
	if err != nil {
		fail("start node-side signer listener/client: %v", err)
	}
	defer client.Close()

	keyPath := filepath.Join(root, "signer_key.json")
	statePath := filepath.Join(root, "signer_state.json")
	signerPV := privval.GenFilePV(keyPath, statePath)
	signerPV.Save()

	signerDialer := privval.NewSignerDialerEndpoint(logger, privval.DialUnixFn(socketPath))
	server := privval.NewSignerServer(signerDialer, chainID, signerPV)
	if err := server.Start(); err != nil {
		fail("start signer-side server: %v", err)
	}
	defer server.Stop()

	if err := client.WaitForConnection(5 * 1e9); err != nil {
		fail("wait for remote signer connection: %v", err)
	}

	pubKey, err := client.GetPubKey()
	if err != nil {
		fail("remote GetPubKey: %v", err)
	}
	expectedPubKey, err := signerPV.GetPubKey()
	if err != nil {
		fail("read expected disposable public key: %v", err)
	}
	if !pubKey.Equals(expectedPubKey) {
		fail("remote public key does not match disposable signer key")
	}

	vote := (&cmttypes.Vote{
		ValidatorAddress: signerPV.GetAddress(),
		ValidatorIndex:   0,
		Height:           1,
		Round:            0,
		Type:             cmtproto.PrevoteType,
		Timestamp:        cmttime.Now(),
		BlockID:          testBlockID("vote"),
	}).ToProto()
	if err := client.SignVote(chainID, vote); err != nil {
		fail("remote SignVote: %v", err)
	}
	if len(vote.Signature) == 0 || !pubKey.VerifySignature(cmttypes.VoteSignBytes(chainID, vote), vote.Signature) {
		fail("remote vote signature is empty or invalid")
	}

	proposal := (&cmttypes.Proposal{
		Height:    2,
		Round:     0,
		BlockID:   testBlockID("proposal"),
		Timestamp: cmttime.Now(),
	}).ToProto()
	if err := client.SignProposal(chainID, proposal); err != nil {
		fail("remote SignProposal: %v", err)
	}
	if len(proposal.Signature) == 0 || !pubKey.VerifySignature(cmttypes.ProposalSignBytes(chainID, proposal), proposal.Signature) {
		fail("remote proposal signature is empty or invalid")
	}

	wrongChainVote := (&cmttypes.Vote{
		ValidatorAddress: signerPV.GetAddress(),
		ValidatorIndex:   0,
		Height:           3,
		Round:            0,
		Type:             cmtproto.PrevoteType,
		Timestamp:        cmttime.Now(),
		BlockID:          testBlockID("wrong-chain"),
	}).ToProto()
	if err := client.SignVote(chainID+"-wrong", wrongChainVote); err == nil {
		fail("wrong-chain-ID signing request was not rejected")
	}

	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_PROTOCOL_PROBE_OK")
}
