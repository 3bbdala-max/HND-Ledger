// hnd-cometbft-remote-only is a CometBFT v0.40.0 CLI whose node provider
// refuses to construct or load a local consensus FilePV. It is intended only
// for HND external-signer integration tests until the runtime is fully reviewed.
package main

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	cmd "github.com/cometbft/cometbft/cmd/cometbft/commands"
	"github.com/cometbft/cometbft/cmd/cometbft/commands/debug"
	cfg "github.com/cometbft/cometbft/config"
	"github.com/cometbft/cometbft/crypto"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	"github.com/cometbft/cometbft/libs/cli"
	"github.com/cometbft/cometbft/libs/log"
	"github.com/cometbft/cometbft/node"
	"github.com/cometbft/cometbft/p2p"
	"github.com/cometbft/cometbft/proxy"
	"github.com/cometbft/cometbft/types"
)

var errRemoteSignerRequired = errors.New("HND remote-only node requires priv_validator_laddr")
var errUnsupportedSignerTransport = errors.New("HND remote-only node permits only absolute unix:// or authenticated noise:// signer endpoints")

func validateRemoteSignerEndpoint(addr string) error {
	if addr == "" {
		return errRemoteSignerRequired
	}
	if strings.HasPrefix(addr, "unix://") {
		if !filepath.IsAbs(strings.TrimPrefix(addr, "unix://")) {
			return errUnsupportedSignerTransport
		}
		return nil
	}
	parsed, err := url.Parse(addr)
	if err != nil || parsed.Scheme != "noise" || parsed.User == nil || parsed.User.Username() == "" {
		return errUnsupportedSignerTransport
	}
	host, port, err := net.SplitHostPort(parsed.Host)
	if err != nil || host == "" {
		return errUnsupportedSignerTransport
	}
	portNumber, err := strconv.Atoi(port)
	if err != nil || portNumber < 1 || portNumber > 65535 {
		return errUnsupportedSignerTransport
	}
	return nil
}

// denyLocalPV is deliberately incapable of returning a public key or signing.
// node.NewNodeWithContext replaces it with the configured remote signer client
// before asking for the validator public key. If that replacement ever changes,
// startup fails closed rather than creating a local consensus key.
type denyLocalPV struct{}

func (denyLocalPV) GetPubKey() (crypto.PubKey, error) {
	return nil, errors.New("local consensus validator is disabled; configure an external signer")
}
func (denyLocalPV) SignVote(string, *cmtproto.Vote) error {
	return errors.New("local consensus signing is disabled")
}
func (denyLocalPV) SignProposal(string, *cmtproto.Proposal) error {
	return errors.New("local consensus signing is disabled")
}

func remoteOnlyNewNode(config *cfg.Config, logger log.Logger) (*node.Node, error) {
	if err := validateRemoteSignerEndpoint(config.PrivValidatorListenAddr); err != nil {
		return nil, err
	}
	// This is the P2P transport identity, not a consensus signing key.
	nodeKey, err := p2p.LoadOrGenNodeKey(config.NodeKeyFile())
	if err != nil {
		return nil, fmt.Errorf("load or generate P2P node key: %w", err)
	}
	return node.NewNode(
		config,
		denyLocalPV{},
		nodeKey,
		proxy.DefaultClientCreator(config.ProxyApp, config.ABCI, config.DBDir()),
		node.DefaultGenesisDocProviderFunc(config),
		cfg.DefaultDBProvider,
		node.DefaultMetricsProvider(config.Instrumentation),
		logger,
	)
}

func main() {
	rootCmd := cmd.RootCmd
	// Keep this CLI intentionally narrow. In particular, do not register
	// InitFilesCmd, GenValidatorCmd, ResetPrivValidatorCmd, TestnetFilesCmd,
	// or other commands that can create, replace, or reset consensus keys.
	rootCmd.AddCommand(
		cmd.ShowNodeIDCmd,
		cmd.VersionCmd,
		debug.DebugCmd,
		cli.NewCompletionCmd(rootCmd, true),
	)
	rootCmd.AddCommand(cmd.NewRunNodeCmd(remoteOnlyNewNode))
	root := cli.PrepareBaseCmd(rootCmd, "CMT", os.ExpandEnv(filepath.Join("$HOME", cfg.DefaultCometDir)))
	if err := root.Execute(); err != nil {
		panic(err)
	}
}

// Keep the interface assertion close to the implementation so API drift fails
// the pinned-source build.
var _ types.PrivValidator = denyLocalPV{}
