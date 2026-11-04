// Persistent Noise-authenticated remote signer for disposable CometBFT v0.40.0 integration tests.
// Test-only: loopback endpoints and ephemeral identities; never use in production.
package main

import (
 "context"
 "encoding/base64"
 "fmt"
 "net"
 "os"
 "os/signal"
 "syscall"
 "time"

 cmted "github.com/cometbft/cometbft/crypto/ed25519"
 "github.com/cometbft/cometbft/libs/log"
 "github.com/cometbft/cometbft/lp2p"
 "github.com/cometbft/cometbft/p2p"
 "github.com/cometbft/cometbft/privval"
 "github.com/cometbft/cometbft/types"
 "github.com/libp2p/go-libp2p/core/peer"
 libp2pnoise "github.com/libp2p/go-libp2p/p2p/security/noise"
)

func die(f string, a ...any) { fmt.Fprintf(os.Stderr,"HND_NOISE_SIGNER_FAILED: "+f+"\n",a...); os.Exit(1) }

func loadSignerIdentity(path string) cmted.PrivKey {
 b,err:=os.ReadFile(path); if err!=nil { die("read signer transport identity: %v",err) }
 raw,err:=base64.StdEncoding.DecodeString(string(b)); if err!=nil { die("decode signer transport identity: %v",err) }
 if len(raw)!=64 { die("invalid signer transport identity length %d",len(raw)) }
 return cmted.PrivKey(raw)
}

func makeDialer(addr string, signerKey cmted.PrivKey, expectedNode peer.ID) privval.SocketDialer {
 return func()(net.Conn,error){
  key,err:=lp2p.PrivateKeyFromCosmosKey(signerKey); if err!=nil{return nil,err}
  transport,err:=libp2pnoise.New(libp2pnoise.ID,key,nil); if err!=nil{return nil,err}
  raw,err:=net.DialTimeout("tcp",addr,2*time.Second); if err!=nil{return nil,err}
  ctx,cancel:=context.WithTimeout(context.Background(),4*time.Second); defer cancel()
  secured,err:=transport.SecureOutbound(ctx,raw,expectedNode); if err!=nil{_ = raw.Close();return nil,err}
  return secured,nil
 }
}

func probeUnauthorized(addr,nodeKeyPath string) {
 nodeKey,err:=p2p.LoadNodeKey(nodeKeyPath); if err!=nil {die("load node identity for unauthorized probe: %v",err)}
 expected,err:=lp2p.IDFromPrivateKey(nodeKey.PrivKey); if err!=nil {die("derive node peer ID for unauthorized probe: %v",err)}
 unauthorized:=cmted.GenPrivKey()
 key,err:=lp2p.PrivateKeyFromCosmosKey(unauthorized); if err!=nil {die("convert unauthorized identity: %v",err)}
 transport,err:=libp2pnoise.New(libp2pnoise.ID,key,nil); if err!=nil {die("create unauthorized Noise transport: %v",err)}
 raw,err:=net.DialTimeout("tcp",addr,2*time.Second); if err!=nil {die("dial validator Noise listener: %v",err)}
 ctx,cancel:=context.WithTimeout(context.Background(),4*time.Second)
 secured,handshakeErr:=transport.SecureOutbound(ctx,raw,expected); cancel()
 // On an authentication failure Noise may return a partially initialized
 // session together with an error. Closing that session can panic; close the
 // raw socket instead and treat the handshake error as the expected rejection.
 if handshakeErr==nil {
  if secured!=nil { _=secured.Close() }
  _=raw.Close()
  die("unauthorized peer was not rejected")
 }
 _=raw.Close()
 fmt.Println("HND_NOISE_REMOTE_SIGNER_UNAUTHORIZED_REJECTED")
}

func main(){
 if len(os.Args)==4 && os.Args[1]=="--probe-unauthorized" { probeUnauthorized(os.Args[2],os.Args[3]); return }
 if len(os.Args)==3 && os.Args[1]=="--generate-noise-identity" {
  key:=cmted.GenPrivKey()
  if err:=os.WriteFile(os.Args[2],[]byte(base64.StdEncoding.EncodeToString(key)),0600); err!=nil {die("write identity: %v",err)}
  id,err:=lp2p.IDFromPrivateKey(key); if err!=nil {die("derive peer ID: %v",err)}
  fmt.Println(id.String()); return
 }
 if len(os.Args)!=8 || os.Args[1]!="--serve-noise" {
  die("usage: --generate-noise-identity <identity-file> | --serve-noise <listen-addr> <node-key-file> <signer-identity-file> <validator-key-file> <validator-state-file> <chain-id>")
 }
 listenAddr,nodeKeyPath,identityPath,pvKeyPath,pvStatePath,chainID:=os.Args[2],os.Args[3],os.Args[4],os.Args[5],os.Args[6],os.Args[7]
 nodeKey,err:=p2p.LoadNodeKey(nodeKeyPath); if err!=nil {die("load node P2P identity: %v",err)}
 expectedNode,err:=lp2p.IDFromPrivateKey(nodeKey.PrivKey); if err!=nil {die("derive expected node peer ID: %v",err)}
 signerKey:=loadSignerIdentity(identityPath)
 signerID,err:=lp2p.IDFromPrivateKey(signerKey); if err!=nil {die("derive signer peer ID: %v",err)}
 _=signerID
 pv:=privval.LoadFilePV(pvKeyPath,pvStatePath)
 dialer:=privval.NewSignerDialerEndpoint(log.NewNopLogger(),makeDialer(listenAddr,signerKey,expectedNode),privval.SignerDialerEndpointConnRetries(100),privval.SignerDialerEndpointRetryWaitInterval(50*time.Millisecond))
 server:=privval.NewSignerServer(dialer,chainID,types.PrivValidator(pv))
 if err:=server.Start(); err!=nil {die("start Noise remote signer: %v",err)}
 deadline:=time.Now().Add(20*time.Second)
 for !dialer.IsConnected() && time.Now().Before(deadline){time.Sleep(50*time.Millisecond)}
 if !dialer.IsConnected(){die("Noise signer did not connect to pinned node identity %s",expectedNode)}
 fmt.Println("HND_NOISE_REMOTE_SIGNER_CONNECTED")
 signals:=make(chan os.Signal,1); signal.Notify(signals,os.Interrupt,syscall.SIGTERM); defer signal.Stop(signals)
 <-signals
 if err:=server.Stop(); err!=nil {die("stop Noise signer: %v",err)}
}
