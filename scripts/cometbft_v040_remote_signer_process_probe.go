// Process-isolated disposable remote-signer smoke test for CometBFT v0.40.0.
// Run from the pinned CometBFT source module:
//   go run <this-file>
// The signer is a child process and uses a private temporary Unix socket.
// Unix sockets are unencrypted: this tests process separation and protocol
// behavior, not authenticated network transport or production key custody.
package main

import (
	"bytes"
	"sync"
	"crypto/sha256"
	"encoding/hex"
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

func runSignerChild(socketPath, keyPath, statePath string, withholdVotes, loadExisting bool) {
	logger := log.NewNopLogger()
	var pv *privval.FilePV
	if loadExisting {
		pv = privval.LoadFilePV(keyPath, statePath)
	} else {
		pv = privval.GenFilePV(keyPath, statePath)
		pv.Save()
	}
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


func runRemoteAntiDoubleSignProbe() {
	root, err := os.MkdirTemp("", "hnd-remote-signer-anti-double-v040-")
	if err != nil { fail("create anti-double-sign probe directory: %v", err) }
	defer os.RemoveAll(root)
	socketPath := filepath.Join(root, "privval.sock")
	rawListener, err := net.Listen("unix", socketPath)
	if err != nil { fail("listen for anti-double-sign signer: %v", err) }
	defer rawListener.Close()
	if err := os.Chmod(socketPath, 0o600); err != nil { fail("restrict anti-double-sign socket: %v", err) }
	endpoint := privval.NewSignerListenerEndpoint(log.NewNopLogger(), privval.NewUnixListener(rawListener))
	client, err := privval.NewSignerClient(endpoint, chainID)
	if err != nil { fail("create anti-double-sign client: %v", err) }
	defer client.Close()
	executable, err := os.Executable()
	if err != nil { fail("resolve anti-double-sign executable: %v", err) }
	keyPath, statePath := filepath.Join(root, "key.json"), filepath.Join(root, "state.json")
	startChild := func(load bool) *exec.Cmd {
		args := []string{"--signer-child", socketPath, keyPath, statePath}
		if load { args = append(args, "--load-existing") }
		cmd := exec.Command(executable, args...)
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		if err := cmd.Start(); err != nil { fail("start anti-double-sign signer child: %v", err) }
		return cmd
	}
	child := startChild(false)
	if err := client.WaitForConnection(10*time.Second); err != nil { fail("wait for first anti-double-sign signer: %v", err) }
	pubKey, err := client.GetPubKey()
	if err != nil { fail("get anti-double-sign public key: %v", err) }
	makeVote := func(label string) *cmtproto.Vote {
		return (&cmttypes.Vote{ValidatorAddress: cmttypes.Address(pubKey.Address()), ValidatorIndex: 0, Height: 44, Round: 2, Type: cmtproto.PrevoteType, Timestamp: cmttime.Now(), BlockID: blockID(label)}).ToProto()
	}
	first := makeVote("anti-double-A")
	if err := client.SignVote(chainID, first); err != nil { fail("first remote vote signature: %v", err) }
	if len(first.Signature) == 0 || !pubKey.VerifySignature(cmttypes.VoteSignBytes(chainID, first), first.Signature) { fail("first remote vote signature is invalid") }
	firstSig := append([]byte(nil), first.Signature...)
	retry := makeVote("anti-double-A")
	if err := client.SignVote(chainID, retry); err != nil { fail("identical remote vote retry: %v", err) }
	if !bytes.Equal(firstSig, retry.Signature) { fail("identical remote retry did not reuse persisted signature") }
	conflict := makeVote("anti-double-B")
	if err := client.SignVote(chainID, conflict); err == nil { fail("remote signer accepted conflicting vote at identical H/R/type") }
	if err := child.Process.Signal(syscall.SIGTERM); err != nil { fail("stop first remote signer: %v", err) }
	if err := child.Wait(); err != nil { fail("wait for first remote signer exit: %v", err) }
	deadline := time.Now().Add(5*time.Second)
	for client.IsConnected() && time.Now().Before(deadline) { time.Sleep(25*time.Millisecond) }
	child = startChild(true)
	if err := client.WaitForConnection(10*time.Second); err != nil { fail("wait for restarted anti-double-sign signer: %v", err) }
	restartedPub, err := client.GetPubKey()
	if err != nil { fail("get public key after signer restart: %v", err) }
	if !bytes.Equal(pubKey.Bytes(), restartedPub.Bytes()) { fail("remote signer identity changed after restart") }
	retryAfterRestart := makeVote("anti-double-A")
	if err := client.SignVote(chainID, retryAfterRestart); err != nil { fail("identical remote retry after restart: %v", err) }
	if !bytes.Equal(firstSig, retryAfterRestart.Signature) { fail("restarted remote signer did not reuse persisted signature") }
	conflictAfterRestart := makeVote("anti-double-B")
	if err := client.SignVote(chainID, conflictAfterRestart); err == nil { fail("restarted remote signer accepted conflicting vote") }
	_ = child.Process.Signal(syscall.SIGTERM)
	_ = child.Wait()
	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_ANTI_DOUBLE_SIGN_RESTART_OK")
}

// runConcurrentSharedFilePVProbe deliberately starts two independent signer
// processes with the same key/state files. It is a negative security probe:
// if both processes emit valid signatures for conflicting blocks at the same
// H/R/type, cross-process single-writer ownership is not enforced.
func runConcurrentSharedFilePVProbe() {
	root, err := os.MkdirTemp("", "hnd-shared-filepv-dual-writer-")
	if err != nil { fail("create shared FilePV probe directory: %v", err) }
	defer os.RemoveAll(root)

	keyPath, statePath := filepath.Join(root, "key.json"), filepath.Join(root, "state.json")
	pv := privval.GenFilePV(keyPath, statePath)
	pv.Save()
	expectedDigest, err := fileSHA256(statePath)
	if err != nil { fail("hash initial shared FilePV state: %v", err) }

	type signerClient struct {
		client *privval.SignerClient
		listener net.Listener
		child *exec.Cmd
	}
	signers := make([]signerClient, 2)
	executable, err := os.Executable()
	if err != nil { fail("resolve shared FilePV probe executable: %v", err) }
	for i := range signers {
		socketPath := filepath.Join(root, fmt.Sprintf("signer-%d.sock", i))
		listener, listenErr := net.Listen("unix", socketPath)
		if listenErr != nil { fail("listen for shared FilePV signer %d: %v", i, listenErr) }
		if chmodErr := os.Chmod(socketPath, 0o600); chmodErr != nil { fail("restrict shared FilePV socket %d: %v", i, chmodErr) }
		endpoint := privval.NewSignerListenerEndpoint(log.NewNopLogger(), privval.NewUnixListener(listener))
		client, clientErr := privval.NewSignerClient(endpoint, chainID)
		if clientErr != nil { fail("create shared FilePV client %d: %v", i, clientErr) }
		child := exec.Command(executable, "--serve-recovery", socketPath, keyPath, statePath, chainID, expectedDigest)
		child.Stdout, child.Stderr = os.Stdout, os.Stderr
		if startErr := child.Start(); startErr != nil { fail("start shared FilePV signer process %d: %v", i, startErr) }
		signers[i] = signerClient{client: client, listener: listener, child: child}
	}
	defer func() {
		for i := range signers {
			_ = signers[i].client.Close()
			_ = signers[i].listener.Close()
			if signers[i].child.Process != nil {
				_ = signers[i].child.Process.Signal(syscall.SIGTERM)
				_ = signers[i].child.Wait()
			}
		}
	}()

	// Both child processes must have loaded the same initial state before either
	// request is sent. Connection establishment occurs after LoadFilePV.
	for i := range signers {
		if err := signers[i].client.WaitForConnection(10 * time.Second); err != nil {
			fail("wait for shared FilePV signer %d connection: %v", i, err)
		}
	}
	pubKeys := make([]cmttypes.PubKey, 2)
	for i := range signers {
		pubKey, err := signers[i].client.GetPubKey()
		if err != nil { fail("get shared FilePV signer %d public key: %v", i, err) }
		pubKeys[i] = pubKey
	}
	if !bytes.Equal(pubKeys[0].Bytes(), pubKeys[1].Bytes()) {
		fail("shared FilePV signer processes do not expose the same validator key")
	}

	makeVote := func(label string) *cmtproto.Vote {
		return (&cmttypes.Vote{
			ValidatorAddress: cmttypes.Address(pubKeys[0].Address()),
			ValidatorIndex: 0, Height: 77, Round: 3, Type: cmtproto.PrevoteType,
			Timestamp: cmttime.Now(), BlockID: blockID(label),
		}).ToProto()
	}
	votes := []*cmtproto.Vote{makeVote("shared-state-conflict-A"), makeVote("shared-state-conflict-B")}
	start := make(chan struct{})
	errs := make([]error, 2)
	var wg sync.WaitGroup
	for i := range signers {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			<-start
			errs[i] = signers[i].client.SignVote(chainID, votes[i])
		}(i)
	}
	close(start)
	wg.Wait()

	for i := range votes {
		if errs[i] != nil { fail("shared FilePV signer %d rejected concurrent vote: %v", i, errs[i]) }
		if len(votes[i].Signature) == 0 || !pubKeys[i].VerifySignature(cmttypes.VoteSignBytes(chainID, votes[i]), votes[i].Signature) {
			fail("shared FilePV signer %d did not return a valid conflicting signature", i)
		}
	}
	if bytes.Equal(votes[0].Signature, votes[1].Signature) {
		fail("conflicting vote requests unexpectedly returned identical signatures")
	}
	fmt.Println("HND_REMOTE_SIGNER_SHARED_FILEPV_DUAL_SIGN_REPRODUCED_UNSAFE: two independent processes signed conflicting blocks at identical H/R/type")
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

func fileSHA256(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil { return "", err }
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}

func runPersistentSigner(socketPath, keyPath, statePath, signerChainID, expectedStateDigest string, requireExistingState bool) {
	if _, err := os.Stat(keyPath); err != nil {
		fail("signer key file unavailable: %v", err)
	}
	stateInfo, stateErr := os.Stat(statePath)
	if os.IsNotExist(stateErr) {
		if requireExistingState {
			fail("recovery mode requires existing anti-double-sign state file")
		}
		// First boot only: initialize signer-owned last-sign state.
		pv := privval.LoadFilePVEmptyState(keyPath, statePath)
		pv.Save()
	} else if stateErr != nil {
		fail("inspect anti-double-sign state file: %v", stateErr)
	} else if !stateInfo.Mode().IsRegular() {
		fail("anti-double-sign state path is not a regular file")
	}
	if requireExistingState {
		if expectedStateDigest == "" {
			fail("recovery mode requires expected anti-double-sign state SHA-256")
		}
		actualDigest, err := fileSHA256(statePath)
		if err != nil { fail("hash anti-double-sign state file: %v", err) }
		if actualDigest != expectedStateDigest {
			fail("anti-double-sign state digest mismatch; refusing recovery")
		}
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

func runMissingSignerRecoveryStateProbe() {
	root, err := os.MkdirTemp("", "hnd-missing-signer-recovery-state-")
	if err != nil { fail("create missing-state probe directory: %v", err) }
	defer os.RemoveAll(root)
	keyPath := filepath.Join(root, "validator_key.json")
	statePath := filepath.Join(root, "missing_state.json")
	pv := privval.GenFilePV(keyPath, filepath.Join(root, "initial_state.json"))
	pv.Save()
	if err := os.Remove(filepath.Join(root, "initial_state.json")); err != nil { fail("remove disposable signer state: %v", err) }
	executable, err := os.Executable()
	if err != nil { fail("resolve signer probe executable: %v", err) }
	child := exec.Command(executable, "--serve-recovery", filepath.Join(root, "unused.sock"), keyPath, statePath, "hnd-missing-state-probe", "expected-digest-placeholder")
	output, runErr := child.CombinedOutput()
	if runErr == nil { fail("recovery signer unexpectedly initialized a missing anti-double-sign state file") }
	if !bytes.Contains(output, []byte("recovery mode requires existing anti-double-sign state file")) {
		fail("missing-state recovery rejected for an unexpected reason: %s", output)
	}
	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_MISSING_STATE_REJECTED")
}

func runStateDigestMismatchProbe() {
	root, err := os.MkdirTemp("", "hnd-signer-state-digest-mismatch-")
	if err != nil { fail("create digest-mismatch probe directory: %v", err) }
	defer os.RemoveAll(root)
	keyA, stateA := filepath.Join(root, "key-a.json"), filepath.Join(root, "state-a.json")
	keyB, stateB := filepath.Join(root, "key-b.json"), filepath.Join(root, "state-b.json")
	privval.GenFilePV(keyA, stateA).Save()
	pvB := privval.GenFilePV(keyB, stateB)
	pvB.Save()
	substituteVote := (&cmttypes.Vote{
		ValidatorAddress: cmttypes.Address(pvB.Key.PubKey.Address()),
		Height: 1, Round: 0, Type: cmtproto.PrevoteType,
		Timestamp: cmttime.Now(), BlockID: blockID("substituted-state"),
	}).ToProto()
	if err := pvB.SignVote(chainID, substituteVote); err != nil {
		fail("advance disposable substitute signer state: %v", err)
	}
	expected, err := fileSHA256(stateA)
	if err != nil { fail("hash expected signer state: %v", err) }
	executable, err := os.Executable()
	if err != nil { fail("resolve signer helper executable: %v", err) }
	child := exec.Command(executable, "--serve-recovery", filepath.Join(root, "unused.sock"), keyB, stateB, chainID, expected)
	output, runErr := child.CombinedOutput()
	if runErr == nil { fail("recovery accepted substituted but parseable signer state") }
	if !bytes.Contains(output, []byte("anti-double-sign state digest mismatch; refusing recovery")) {
		fail("substituted signer state rejected for unexpected reason: %s", output)
	}
	fmt.Println("COMETBFT_V040_REMOTE_SIGNER_STATE_DIGEST_MISMATCH_REJECTED")
}

func main() {
	if len(os.Args) > 1 && (os.Args[1] == "--serve" || os.Args[1] == "--serve-recovery") {
		expectedDigest := ""
		if os.Args[1] == "--serve" && len(os.Args) != 6 {
			fail("usage: --serve <socket> <key-file> <state-file> <chain-id>")
		}
		if os.Args[1] == "--serve-recovery" && len(os.Args) != 7 {
			fail("usage: --serve-recovery <socket> <key-file> <state-file> <chain-id> <expected-state-sha256>")
		}
		if os.Args[1] == "--serve-recovery" { expectedDigest = os.Args[6] }
		runPersistentSigner(os.Args[2], os.Args[3], os.Args[4], os.Args[5], expectedDigest, os.Args[1] == "--serve-recovery")
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "--state-digest-mismatch-probe" {
		runStateDigestMismatchProbe()
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "--missing-state-recovery-probe" {
		runMissingSignerRecoveryStateProbe()
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "--remote-anti-double-sign-probe" {
		runRemoteAntiDoubleSignProbe()
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
		runSignerChild(os.Args[2], os.Args[3], os.Args[4], withhold, len(os.Args) == 6 && os.Args[5] == "--load-existing")
		return
	}
	runNodeParent()
}
