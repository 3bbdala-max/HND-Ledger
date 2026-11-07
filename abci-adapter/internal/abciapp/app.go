package abciapp

import (
	"context"

	"github.com/cometbft/cometbft/abci/types"

	"github.com/3bbdala-max/HND-Ledger/abci-adapter/internal/ipc"
)

// HNDApp is deliberately a transport adapter. All transaction, state,
// consensus-application, and persistence decisions are delegated to Python.
type HNDApp struct {
	client *ipc.Client
}

var _ types.Application = (*HNDApp)(nil)

func New(client *ipc.Client) *HNDApp { return &HNDApp{client: client} }

func (a *HNDApp) call(ctx context.Context, method string, req, resp any) error {
	return a.client.Call(ctx, method, req, resp)
}

func (a *HNDApp) Info(ctx context.Context, req *types.RequestInfo) (*types.ResponseInfo, error) {
	resp := new(types.ResponseInfo)
	if err := a.call(ctx, "Info", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) Query(ctx context.Context, req *types.RequestQuery) (*types.ResponseQuery, error) {
	resp := new(types.ResponseQuery)
	if err := a.call(ctx, "Query", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) CheckTx(ctx context.Context, req *types.RequestCheckTx) (*types.ResponseCheckTx, error) {
	resp := new(types.ResponseCheckTx)
	if err := a.call(ctx, "CheckTx", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) InsertTx(ctx context.Context, req *types.RequestInsertTx) (*types.ResponseInsertTx, error) {
	resp := new(types.ResponseInsertTx)
	if err := a.call(ctx, "InsertTx", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) ReapTxs(ctx context.Context, req *types.RequestReapTxs) (*types.ResponseReapTxs, error) {
	resp := new(types.ResponseReapTxs)
	if err := a.call(ctx, "ReapTxs", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) InitChain(ctx context.Context, req *types.RequestInitChain) (*types.ResponseInitChain, error) {
	resp := new(types.ResponseInitChain)
	if err := a.call(ctx, "InitChain", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) PrepareProposal(ctx context.Context, req *types.RequestPrepareProposal) (*types.ResponsePrepareProposal, error) {
	resp := new(types.ResponsePrepareProposal)
	if err := a.call(ctx, "PrepareProposal", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) ProcessProposal(ctx context.Context, req *types.RequestProcessProposal) (*types.ResponseProcessProposal, error) {
	resp := new(types.ResponseProcessProposal)
	if err := a.call(ctx, "ProcessProposal", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) FinalizeBlock(ctx context.Context, req *types.RequestFinalizeBlock) (*types.ResponseFinalizeBlock, error) {
	resp := new(types.ResponseFinalizeBlock)
	if err := a.call(ctx, "FinalizeBlock", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) ExtendVote(ctx context.Context, req *types.RequestExtendVote) (*types.ResponseExtendVote, error) {
	resp := new(types.ResponseExtendVote)
	if err := a.call(ctx, "ExtendVote", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) VerifyVoteExtension(ctx context.Context, req *types.RequestVerifyVoteExtension) (*types.ResponseVerifyVoteExtension, error) {
	resp := new(types.ResponseVerifyVoteExtension)
	if err := a.call(ctx, "VerifyVoteExtension", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) Commit(ctx context.Context, req *types.RequestCommit) (*types.ResponseCommit, error) {
	resp := new(types.ResponseCommit)
	if err := a.call(ctx, "Commit", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) ListSnapshots(ctx context.Context, req *types.RequestListSnapshots) (*types.ResponseListSnapshots, error) {
	resp := new(types.ResponseListSnapshots)
	if err := a.call(ctx, "ListSnapshots", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) OfferSnapshot(ctx context.Context, req *types.RequestOfferSnapshot) (*types.ResponseOfferSnapshot, error) {
	resp := new(types.ResponseOfferSnapshot)
	if err := a.call(ctx, "OfferSnapshot", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) LoadSnapshotChunk(ctx context.Context, req *types.RequestLoadSnapshotChunk) (*types.ResponseLoadSnapshotChunk, error) {
	resp := new(types.ResponseLoadSnapshotChunk)
	if err := a.call(ctx, "LoadSnapshotChunk", req, resp); err != nil { return nil, err }
	return resp, nil
}

func (a *HNDApp) ApplySnapshotChunk(ctx context.Context, req *types.RequestApplySnapshotChunk) (*types.ResponseApplySnapshotChunk, error) {
	resp := new(types.ResponseApplySnapshotChunk)
	if err := a.call(ctx, "ApplySnapshotChunk", req, resp); err != nil { return nil, err }
	return resp, nil
}
