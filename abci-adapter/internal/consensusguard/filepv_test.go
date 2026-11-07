package consensusguard

import (
	"bytes"
	"path/filepath"
	"testing"
	"time"

	"github.com/cometbft/cometbft/crypto/ed25519"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
)

func TestFilePVRecoversSignatureAndRejectsConflictingVoteAfterReload(t *testing.T) {
	dir := t.TempDir()
	keyPath := filepath.Join(dir, "priv_validator_key.json")
	statePath := filepath.Join(dir, "priv_validator_state.json")

	pv := privval.NewFilePV(ed25519.GenPrivKey(), keyPath, statePath)
	pv.Save()

	vote := func(blockByte byte) *cmtproto.Vote {
		return &cmtproto.Vote{
			Type:  cmtproto.PrevoteType,
			Height: 9,
			Round:  2,
			BlockID: cmtproto.BlockID{
				Hash: bytes.Repeat([]byte{blockByte}, 32),
				PartSetHeader: cmtproto.PartSetHeader{
					Total: 1,
					Hash:  bytes.Repeat([]byte{blockByte + 1}, 32),
				},
			},
			Timestamp: time.Date(2026, 11, 7, 12, 0, 0, 0, time.UTC),
		}
	}

	first := vote(0x11)
	if err := pv.SignVote("HND-LOCAL-V2", first); err != nil {
		t.Fatalf("initial vote signing failed: %v", err)
	}
	if len(first.Signature) == 0 {
		t.Fatal("initial vote has no signature")
	}

	// Simulate process loss after the private validator has persisted the
	// signature but before the consensus message is safely processed.
	restarted := privval.LoadFilePV(keyPath, statePath)
	retry := vote(0x11)
	if err := restarted.SignVote("HND-LOCAL-V2", retry); err != nil {
		t.Fatalf("same H/R/S vote should reuse persisted signature: %v", err)
	}
	if !bytes.Equal(retry.Signature, first.Signature) {
		t.Fatal("restart did not reuse the original persisted signature")
	}

	conflict := vote(0x22)
	if err := restarted.SignVote("HND-LOCAL-V2", conflict); err == nil {
		t.Fatal("conflicting block vote at the same height/round/step was signed")
	}
	if len(conflict.Signature) != 0 {
		t.Fatal("conflicting vote unexpectedly received a signature")
	}
}
