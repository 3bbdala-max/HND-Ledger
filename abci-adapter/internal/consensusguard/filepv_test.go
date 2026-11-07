package consensusguard

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	"github.com/cometbft/cometbft/crypto/ed25519"
	"github.com/cometbft/cometbft/privval"
	cmtproto "github.com/cometbft/cometbft/proto/tendermint/types"
)

func filePVVote(blockByte byte) *cmtproto.Vote {
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

func TestFilePVRecoversSignatureAndRejectsConflictingVoteAfterProcessExit(t *testing.T) {
	keyPath := os.Getenv("HND_FILEPV_KEY")
	statePath := os.Getenv("HND_FILEPV_STATE")
	signaturePath := os.Getenv("HND_FILEPV_SIGNATURE")

	// Child mode: sign once, persist through FilePV, export the signed bytes,
	// then terminate immediately without running test cleanup.
	if os.Getenv("HND_FILEPV_CRASH_HELPER") == "1" {
		pv := privval.LoadFilePV(keyPath, statePath)
		vote := filePVVote(0x11)
		if err := pv.SignVote("HND-LOCAL-V2", vote); err != nil {
			t.Fatalf("child signing failed: %v", err)
		}
		if err := os.WriteFile(signaturePath, vote.Signature, 0o600); err != nil {
			t.Fatalf("write child signature: %v", err)
		}
		os.Exit(0)
	}

	dir := t.TempDir()
	keyPath = filepath.Join(dir, "priv_validator_key.json")
	statePath = filepath.Join(dir, "priv_validator_state.json")
	signaturePath = filepath.Join(dir, "signed-vote.bin")

	pv := privval.NewFilePV(ed25519.GenPrivKey(), keyPath, statePath)
	pv.Save()

	cmd := exec.Command(os.Args[0], "-test.run=^TestFilePVRecoversSignatureAndRejectsConflictingVoteAfterProcessExit$")
	cmd.Env = append(os.Environ(),
		"HND_FILEPV_CRASH_HELPER=1",
		"HND_FILEPV_KEY="+keyPath,
		"HND_FILEPV_STATE="+statePath,
		"HND_FILEPV_SIGNATURE="+signaturePath,
	)
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("signing child process failed: %v\n%s", err, output)
	}
	originalSignature, err := os.ReadFile(signaturePath)
	if err != nil || len(originalSignature) == 0 {
		t.Fatalf("child did not leave a persisted signature: %v", err)
	}

	// The signing process has exited. Reload the on-disk FilePV state in this
	// parent process and verify safe retry plus rejection of equivocation.
	restarted := privval.LoadFilePV(keyPath, statePath)
	retry := filePVVote(0x11)
	if err := restarted.SignVote("HND-LOCAL-V2", retry); err != nil {
		t.Fatalf("same H/R/S vote should reuse persisted signature after process exit: %v", err)
	}
	if !bytes.Equal(retry.Signature, originalSignature) {
		t.Fatal("restart did not reuse the original persisted signature")
	}

	conflict := filePVVote(0x22)
	if err := restarted.SignVote("HND-LOCAL-V2", conflict); err == nil {
		t.Fatal("conflicting block vote at the same height/round/step was signed")
	}
	if len(conflict.Signature) != 0 {
		t.Fatal("conflicting vote unexpectedly received a signature")
	}
}
