// Disposable integration smoke test for CometBFT v0.40.0 FilePV signing safety.
// Run from the pinned CometBFT source module with: go run <this-file>.
package main

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"

	"github.com/cometbft/cometbft/crypto/tmhash"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
	cmttypes "github.com/cometbft/cometbft/types"
	cmttime "github.com/cometbft/cometbft/types/time"
)

const chainID = "hnd-cometbft-v040-signer-guard"

func fail(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "HND_PRIVVAL_SIGNER_GUARD_FAILED: "+format+"\n", args...)
	os.Exit(1)
}

func blockID(label string) cmttypes.BlockID {
	hash := tmhash.Sum([]byte("hnd-block-" + label))
	partHash := tmhash.Sum([]byte("hnd-parts-" + label))
	return cmttypes.BlockID{
		Hash: hash,
		PartSetHeader: cmttypes.PartSetHeader{
			Total: 1,
			Hash:  partHash,
		},
	}
}

func newVote(address cmttypes.Address, height int64, round int32, typ cmtproto.SignedMsgType, block cmttypes.BlockID) *cmtproto.Vote {
	return (&cmttypes.Vote{
		ValidatorAddress: address,
		ValidatorIndex:   0,
		Height:           height,
		Round:            round,
		Type:             typ,
		Timestamp:        cmttime.Now(),
		BlockID:          block,
	}).ToProto()
}

func newProposal(height int64, round int32, block cmttypes.BlockID) *cmtproto.Proposal {
	return (&cmttypes.Proposal{
		Height:    height,
		Round:     round,
		BlockID:   block,
		Timestamp: cmttime.Now(),
	}).ToProto()
}

func requireAccepted(label string, err error) {
	if err != nil {
		fail("%s should be accepted: %v", label, err)
	}
}

func requireRejected(label string, err error) {
	if err == nil {
		fail("%s should have been rejected", label)
	}
}

func testVoteSigning(dir string) {
	keyPath := filepath.Join(dir, "vote_key.json")
	statePath := filepath.Join(dir, "vote_state.json")
	pv := privval.GenFilePV(keyPath, statePath)
	pv.Save()

	blockA, blockB := blockID("vote-A"), blockID("vote-B")
	first := newVote(pv.GetAddress(), 10, 1, cmtproto.PrevoteType, blockA)
	requireAccepted("first prevote", pv.SignVote(chainID, first))
	if len(first.Signature) == 0 {
		fail("first prevote produced no signature")
	}
	firstSignature := append([]byte(nil), first.Signature...)

	duplicate := newVote(pv.GetAddress(), 10, 1, cmtproto.PrevoteType, blockA)
	requireAccepted("identical H/R/type retry", pv.SignVote(chainID, duplicate))
	if !bytes.Equal(firstSignature, duplicate.Signature) {
		fail("identical H/R/type retry did not reuse the persisted signature")
	}
	pubKey, err := pv.GetPubKey()
	if err != nil {
		fail("cannot retrieve validator public key: %v", err)
	}
	if !pubKey.VerifySignature(cmttypes.VoteSignBytes(chainID, duplicate), duplicate.Signature) {
		fail("reused prevote signature did not verify")
	}

	conflict := newVote(pv.GetAddress(), 10, 1, cmtproto.PrevoteType, blockB)
	requireRejected("conflicting block at same vote H/R/type", pv.SignVote(chainID, conflict))

	// Reload the signer from its on-disk key and anti-double-sign state.
	reloaded := privval.LoadFilePV(keyPath, statePath)
	retryAfterRestart := newVote(reloaded.GetAddress(), 10, 1, cmtproto.PrevoteType, blockA)
	requireAccepted("same prevote after signer restart", reloaded.SignVote(chainID, retryAfterRestart))
	if !bytes.Equal(firstSignature, retryAfterRestart.Signature) {
		fail("restarted signer did not reuse the persisted prevote signature")
	}
	conflictAfterRestart := newVote(reloaded.GetAddress(), 10, 1, cmtproto.PrevoteType, blockB)
	requireRejected("conflicting prevote after signer restart", reloaded.SignVote(chainID, conflictAfterRestart))

	lowerRound := newVote(reloaded.GetAddress(), 10, 0, cmtproto.PrevoteType, blockA)
	requireRejected("round regression", reloaded.SignVote(chainID, lowerRound))
	lowerHeight := newVote(reloaded.GetAddress(), 9, 7, cmtproto.PrevoteType, blockA)
	requireRejected("height regression", reloaded.SignVote(chainID, lowerHeight))

	// The HRS step may progress from prevote to precommit for the same block.
	precommit := newVote(reloaded.GetAddress(), 10, 1, cmtproto.PrecommitType, blockA)
	requireAccepted("same H/R precommit step progression", reloaded.SignVote(chainID, precommit))
	reloadedAgain := privval.LoadFilePV(keyPath, statePath)
	conflictingPrecommit := newVote(reloadedAgain.GetAddress(), 10, 1, cmtproto.PrecommitType, blockB)
	requireRejected("conflicting precommit after signer restart", reloadedAgain.SignVote(chainID, conflictingPrecommit))
}

func testProposalSigning(dir string) {
	keyPath := filepath.Join(dir, "proposal_key.json")
	statePath := filepath.Join(dir, "proposal_state.json")
	pv := privval.GenFilePV(keyPath, statePath)
	pv.Save()

	blockA, blockB := blockID("proposal-A"), blockID("proposal-B")
	first := newProposal(20, 2, blockA)
	requireAccepted("first proposal", pv.SignProposal(chainID, first))
	if len(first.Signature) == 0 {
		fail("first proposal produced no signature")
	}
	firstSignature := append([]byte(nil), first.Signature...)

	duplicate := newProposal(20, 2, blockA)
	requireAccepted("identical H/R proposal retry", pv.SignProposal(chainID, duplicate))
	if !bytes.Equal(firstSignature, duplicate.Signature) {
		fail("identical H/R proposal retry did not reuse the persisted signature")
	}

	conflict := newProposal(20, 2, blockB)
	requireRejected("conflicting proposal at same H/R", pv.SignProposal(chainID, conflict))

	reloaded := privval.LoadFilePV(keyPath, statePath)
	conflictAfterRestart := newProposal(20, 2, blockB)
	requireRejected("conflicting proposal after signer restart", reloaded.SignProposal(chainID, conflictAfterRestart))
}

func main() {
	dir, err := os.MkdirTemp("", "hnd-cometbft-v040-privval-")
	if err != nil {
		fail("cannot create temporary directory: %v", err)
	}
	defer os.RemoveAll(dir)

	testVoteSigning(dir)
	testProposalSigning(dir)

	fmt.Println("COMETBFT_V040_PRIVVAL_SIGNER_GUARD_OK")
}
