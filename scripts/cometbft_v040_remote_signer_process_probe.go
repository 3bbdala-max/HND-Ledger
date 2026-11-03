// Process-isolated disposable remote-signer smoke test for CometBFT v0.40.0.
// Run from the pinned CometBFT source module:
//   go run <this-file>
// The signer is a child process and uses a private temporary Unix socket.
// Unix sockets are unencrypted: this tests process separation and protocol
// behavior, not authenticated network transport or production key custody.
package main

import (
	"errors"
	"fmt"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/cometbft/cometbft/crypto/tmhash"
	"github.com/cometbft/cometbft/libs/log"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmttypes "github.com/cometbft/cometbft/types"
	cmttime "github.com/cometbft/cometbft/types/time"
)

const chainID = "hnd-cometbft-v040-remote-signer-process-probe"

type voteWithholdingPV struct { cmttypes.PrivValidator }

func (pv voteWithholdingPV) SignVote(string, *cmtproto.Vote) error {
	return errors.New("test signer intentionally withholds vote signatures")
}

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "HND_REMOTE_SIGNER_PROCESS_PROBE_FAILED: "+format+"\n", args...)
	os.Exit(1)
}

func blockID(label string) cmttypes.BlockID {
	return cmttypes.BlockID{
		Hash: tmhash.Sum([]byte("hnd-remote-signer-process-block-" + label)),
		PartSetHeader: cmttypes.PartSetHeader{
			Total: 1,
			Hash:  tmhash.Sum([]byte("hnd-remote-signer-process-parts-" + label)),
		},
	}
}

func runSignerChild(socketPath, keyPath, statePath string, withholdVotes bool) {
	logger := log.NewNopLogger()
	pv := privval.GenFilePV(keyPath, statePath)
	pv.Save()
	dialer := privval.NewSignerDialerEndpoint(logger, privval.DialUnixFn(socketPath))
	var signer cmttypes.PrivValidator = pv
	if withholdVotes {
		signer = voteWithholdingPV{PrivValidator: pv}
	}
	server := privval.NewSignerServer(dialer, chainID, signer)
	if err := server.Start(); err != nil {
		fail("start child signer server: %v", err)
	}
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	<-signals
	signal.Stop(signals)
	if err := server.Stop(); err != nil {
		fail("stop child signer server: %v", err)
	}
}


func runWithholdingProbe() {
	root, err := os.MkdirTemp("", "hnd-remote-signer-withhold-v040-")
	if err != nil { fail("create withholding probe directory: %v", err) }
	defer os.RemoveAll(root)
	socketPath := filepath.Join(root, "privval.sock")
	rawListener, err := net.Listen("unix", socketPath)
	if err != nil { fail("listen for withholding signer: %v", err) }
	defer rawListener.Close()
	if err := os.Chmod(socketPath, 0o600); err != nil { fail("restrict withholding socket: %v", err) }
	logger := log.NewNopLogger()
	endpoint := privval.NewSignerListenerEndpoint(logger, privval.NewUnixListener(rawListener))
	client, err := privval.NewSignerClient(endpoint, chainID)
	if err != nil { fail("create withholding probe client: %v", err) }
	defer client.Close()
	executable, err := os.Executable()
	if err != nil { fail("resolve probe executable: %v", err) }
	keyPath, statePath := filepath.Join(root, "key.json"), filepath.Join(root, "state.json")
	child := exec.Command(executable, "--signer-child", socketPath, keyPath, statePath, "--withhold-votes")
	child.Stdout, child.Stderr = os.Stdout, os.Stderr
	if err := child.Start(); err != nil { fail("start withholding signer child: %v", err) }
	defer func() { if child.Process != nil { _ = child.Process.Kill(); _ = child.Wait() } }()
	if err := client.WaitForConnection(10*time.Second); err != nil { fail("wait for withholding signer connection: %v", err) }
	if err := client.Ping(); err != nil { fail("withholding signer initial ping: %v", err) }
	pubKey, err := client.GetPubKey()
	if err != nil { fail("withholding signer GetPubKey: %v", err) }
	vote := (&cmttypes.Vote{
		ValidatorAddress: cmttypes.Address(pubKey.Address()), ValidatorIndex: 0,
		Height: 1, Round: 0, Type: cmtproto.PrevoteType,
		Timestamp: cmttime.Now(), BlockID: blockID("withheld-vote"),
	}).ToProto()
	if err := client.SignVote(chainID, vote); err == nil {
		fail("withholding signer unexpectedly signed a vote")
	}
	if len(vote.Signature) != 0 { fail("withholding signer returned a vote signature despite refusal") }
	if err := client.Ping(); err != nil { fail("signer connection did not remain usable after vote refusal: %v", err) }
	if _, err := client.GetPubKey(); err != nil { fail("signer connection lost GetPubKey after vote refusal: %v", err) }
	if child.ProcessState != nil && child.ProcessState.Exited() { fail("withholding signer process exited during probe") }
	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_CONNECTED_WITH_VOTE_WITHHOLDING_OK")
}

func runNodeParent() {
	root, err := os.MkdirTemp("", "hnd-remote-signer-process-v040-")
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
	nodeEndpoint := privval.NewSignerListenerEndpoint(logger, privval.NewUnixListener(rawListener))
	client, err := privval.NewSignerClient(nodeEndpoint, chainID)
	if err != nil {
		fail("start node-side signer client: %v", err)
	}
	defer client.Close()

	executable, err := os.Executable()
	if err != nil {
		fail("resolve current executable: %v", err)
	}
	keyPath := filepath.Join(root, "signer_key.json")
	statePath := filepath.Join(root, "signer_state.json")
	child := exec.Command(executable, "--signer-child", socketPath, keyPath, statePath)
	child.Stdout = os.Stdout
	child.Stderr = os.Stderr
	if err := child.Start(); err != nil {
		fail("start separate signer process: %v", err)
	}
	defer func() {
		if child.Process != nil {
			_ = child.Process.Kill()
			_ = child.Wait()
		}
	}()

	if err := client.WaitForConnection(10 * time.Second); err != nil {
		fail("wait for child signer connection: %v", err)
	}
	if err := client.Ping(); err != nil {
		fail("remote signer ping: %v", err)
	}

	pubKey, err := client.GetPubKey()
	if err != nil {
		fail("remote GetPubKey: %v", err)
	}

	vote := (&cmttypes.Vote{
		ValidatorAddress: cmttypes.Address(pubKey.Address()),
		ValidatorIndex:   0,
		Height:           1,
		Round:            0,
		Type:             cmtproto.PrevoteType,
		Timestamp:        cmttime.Now(),
		BlockID:          blockID("vote"),
	}).ToProto()
	if err := client.SignVote(chainID, vote); err != nil {
		fail("remote SignVote: %v", err)
	}
	if len(vote.Signature) == 0 || !pubKey.VerifySignature(cmttypes.VoteSignBytes(chainID, vote), vote.Signature) {
		fail("child signer returned an invalid vote signature")
	}

	proposal := (&cmttypes.Proposal{
		Height:    2,
		Round:     0,
		BlockID:   blockID("proposal"),
		Timestamp: cmttime.Now(),
	}).ToProto()
	if err := client.SignProposal(chainID, proposal); err != nil {
		fail("remote SignProposal: %v", err)
	}
	if len(proposal.Signature) == 0 || !pubKey.VerifySignature(cmttypes.ProposalSignBytes(chainID, proposal), proposal.Signature) {
		fail("child signer returned an invalid proposal signature")
	}

	wrongChainVote := (&cmttypes.Vote{
		ValidatorIndex: 0,
		Height:         3,
		Round:          0,
		Type:           cmtproto.PrevoteType,
		Timestamp:      cmttime.Now(),
		BlockID:        blockID("wrong-chain"),
	}).ToProto()
	if err := client.SignVote(chainID+"-wrong", wrongChainVote); err == nil {
		fail("child signer accepted a wrong-chain-ID request")
	}

	if child.ProcessState != nil && child.ProcessState.Exited() {
		fail("signer child process exited before the probe completed")
	}
	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_PROCESS_PROBE_OK")
}

func runPersistentSigner(socketPath, keyPath, statePath, signerChainID string) {
	if _, err := os.Stat(keyPath); err != nil {
		fail("signer key file unavailable: %v", err)
	}
	if _, err := os.Stat(statePath); os.IsNotExist(err) {
		// Initialize a signer-owned last-sign state exactly once before service startup.
		pv := privval.LoadFilePVEmptyState(keyPath, statePath)
		pv.Save()
	}
	pv := privval.LoadFilePV(keyPath, statePath)
	logger := log.NewNopLogger()
	dialer := privval.NewSignerDialerEndpoint(
		logger,
		privval.DialUnixFn(socketPath),
		privval.SignerDialerEndpointConnRetries(100),
	)
	server := privval.NewSignerServer(dialer, signerChainID, pv)
	if err := server.Start(); err != nil {
		fail("start persistent signer server: %v", err)
	}
	deadline := time.Now().Add(10 * time.Second)
	for !dialer.IsConnected() && time.Now().Before(deadline) {
		time.Sleep(50 * time.Millisecond)
	}
	if !dialer.IsConnected() {
		fail("remote signer did not establish its node connection")
	}
	fmt.Println("HND_REMOTE_SIGNER_CONNECTED")
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	<-signals
	signal.Stop(signals)
	if err := server.Stop(); err != nil {
		fail("stop persistent signer server: %v", err)
	}
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--serve" {
		if len(os.Args) != 6 {
			fail("usage: --serve <socket> <key-file> <state-file> <chain-id>")
		}
		runPersistentSigner(os.Args[2], os.Args[3], os.Args[4], os.Args[5])
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "--withholding-probe" {
		runWithholdingProbe()
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "--signer-child" {
		if len(os.Args) < 5 || len(os.Args) > 6 {
			fail("usage: --signer-child <socket> <key-file> <state-file> [--withhold-votes]")
		}
		withhold := len(os.Args) == 6 && os.Args[5] == "--withhold-votes"
		runSignerChild(os.Args[2], os.Args[3], os.Args[4], withhold)
		return
	}
	runNodeParent()
}
