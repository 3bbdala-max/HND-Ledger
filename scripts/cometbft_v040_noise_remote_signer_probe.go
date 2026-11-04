// Noise-authenticated remote-signer integration probe for pinned CometBFT v0.40.0.
// Run from the pinned CometBFT source module:
//   go run <this-file>
// Uses disposable keys and loopback only. Never use these test keys in production.
package main

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"time"

	"github.com/cometbft/cometbft/crypto/ed25519"
	"github.com/cometbft/cometbft/crypto/tmhash"
	"github.com/cometbft/cometbft/libs/log"
	"github.com/cometbft/cometbft/lp2p"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmttypes "github.com/cometbft/cometbft/types"
	cmttime "github.com/cometbft/cometbft/types/time"
	"github.com/libp2p/go-libp2p/core/peer"
	libp2pnoise "github.com/libp2p/go-libp2p/p2p/security/noise"
)

const chainID = "hnd-cometbft-v040-noise-remote-signer-probe"

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "HND_NOISE_REMOTE_SIGNER_PROBE_FAILED: "+format+"\n", args...)
	os.Exit(1)
}

func makeNoiseDialer(addr string, signerKey ed25519.PrivKey, expectedNode peer.ID) privval.SocketDialer {
	return func() (net.Conn, error) {
		libp2pKey, err := lp2p.PrivateKeyFromCosmosKey(signerKey)
		if err != nil { return nil, err }
		transport, err := libp2pnoise.New(libp2pnoise.ID, libp2pKey, nil)
		if err != nil { return nil, err }
		raw, err := net.DialTimeout("tcp", addr, 2*time.Second)
		if err != nil { return nil, err }
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		secured, err := transport.SecureOutbound(ctx, raw, expectedNode)
		if err != nil { _ = raw.Close(); return nil, err }
		return secured, nil
	}
}

func blockID() cmttypes.BlockID {
	return cmttypes.BlockID{
		Hash: tmhash.Sum([]byte("hnd-noise-probe-block-hash")),
		PartSetHeader: cmttypes.PartSetHeader{Total: 1, Hash: tmhash.Sum([]byte("hnd-noise-probe-parts-hash"))},
	}
}

func runAuthorizedSignerProbe() {
	root, err := os.MkdirTemp("", "hnd-noise-remote-signer-")
	if err != nil { fail("create temporary directory: %v", err) }
	defer os.RemoveAll(root)

	nodeKey := ed25519.GenPrivKey()
	signerIdentityKey := ed25519.GenPrivKey()
	nodePeerID, err := lp2p.IDFromPrivateKey(nodeKey)
	if err != nil { fail("derive node peer identity: %v", err) }
	signerPeerID, err := lp2p.IDFromPrivateKey(signerIdentityKey)
	if err != nil { fail("derive signer peer identity: %v", err) }

	reservation, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil { fail("reserve loopback port: %v", err) }
	addr := reservation.Addr().String()
	if err := reservation.Close(); err != nil { fail("release reserved port: %v", err) }
	listenAddr := fmt.Sprintf("noise://%s@%s", signerPeerID, addr)

	logger := log.NewNopLogger()
	nodeEndpoint, err := privval.NewSignerListenerFromAddr(listenAddr, nodeKey, logger)
	if err != nil { fail("create allowlisted Noise listener: %v", err) }
	client, err := privval.NewSignerClient(nodeEndpoint, chainID)
	if err != nil { fail("create node-side remote signer client: %v", err) }
	defer client.Close()

	signerDialer := privval.NewSignerDialerEndpoint(
		logger,
		makeNoiseDialer(addr, signerIdentityKey, nodePeerID),
		privval.SignerDialerEndpointConnRetries(100),
		privval.SignerDialerEndpointRetryWaitInterval(50*time.Millisecond),
	)
	pv := privval.GenFilePV(filepath.Join(root, "validator_key.json"), filepath.Join(root, "validator_state.json"))
	pv.Save()
	server := privval.NewSignerServer(signerDialer, chainID, pv)
	if err := server.Start(); err != nil { fail("start remote signer server: %v", err) }
	defer server.Stop()

	if err := client.WaitForConnection(10*time.Second); err != nil { fail("wait for authenticated Noise connection: %v", err) }
	if err := client.Ping(); err != nil { fail("Noise signer ping: %v", err) }
	pubKey, err := client.GetPubKey()
	if err != nil { fail("Noise signer public key: %v", err) }

	vote := (&cmttypes.Vote{
		ValidatorAddress: cmttypes.Address(pubKey.Address()),
		ValidatorIndex: 0, Height: 1, Round: 0, Type: cmtproto.PrevoteType,
		Timestamp: cmttime.Now(), BlockID: blockID(),
	}).ToProto()
	if err := client.SignVote(chainID, vote); err != nil { fail("Noise remote SignVote: %v", err) }
	if len(vote.Signature) == 0 || !pubKey.VerifySignature(cmttypes.VoteSignBytes(chainID, vote), vote.Signature) {
		fail("Noise signer returned an invalid vote signature")
	}
	fmt.Println("COMETBFT_V040_NOISE_REMOTE_SIGNER_AUTHORIZED_OK")
}

func runUnauthorizedPeerRejectionProbe() {
	nodeKey := ed25519.GenPrivKey()
	allowedKey := ed25519.GenPrivKey()
	unauthorizedKey := ed25519.GenPrivKey()
	allowedPeer, err := lp2p.IDFromPrivateKey(allowedKey)
	if err != nil { fail("derive allowlisted peer identity: %v", err) }
	nodePeerID, err := lp2p.IDFromPrivateKey(nodeKey)
	if err != nil { fail("derive rejection-test node identity: %v", err) }

	rawListener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil { fail("listen for unauthorized-peer test: %v", err) }
	noiseListener, err := privval.NewNoiseListener(rawListener, nodeKey, []peer.ID{allowedPeer})
	if err != nil { fail("create non-empty Noise allowlist: %v", err) }
	defer noiseListener.Close()

	accepted := make(chan error, 1)
	go func() {
		conn, acceptErr := noiseListener.Accept()
		if conn != nil { _ = conn.Close() }
		accepted <- acceptErr
	}()

	libp2pKey, err := lp2p.PrivateKeyFromCosmosKey(unauthorizedKey)
	if err != nil { fail("convert unauthorized test identity: %v", err) }
	transport, err := libp2pnoise.New(libp2pnoise.ID, libp2pKey, nil)
	if err != nil { fail("create unauthorized Noise transport: %v", err) }
	raw, err := net.DialTimeout("tcp", rawListener.Addr().String(), 2*time.Second)
	if err != nil { fail("connect unauthorized test peer: %v", err) }
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	secured, handshakeErr := transport.SecureOutbound(ctx, raw, nodePeerID)
	cancel()
	if secured != nil { _ = secured.Close() }
	if handshakeErr != nil { _ = raw.Close() }

	select {
	case acceptErr := <-accepted:
		if acceptErr == nil { fail("Noise listener accepted a peer outside its allowlist") }
	case <-time.After(4*time.Second):
		fail("timed out waiting for allowlist rejection")
	}
	fmt.Println("COMETBFT_V040_NOISE_REMOTE_SIGNER_UNAUTHORIZED_REJECTED")
}

func main() {
	runAuthorizedSignerProbe()
	runUnauthorizedPeerRejectionProbe()
	fmt.Println("COMETBFT_V040_NOISE_REMOTE_SIGNER_PROBE_OK")
}
