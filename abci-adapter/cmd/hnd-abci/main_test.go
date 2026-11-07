package main

import "testing"

func TestValidateListenAddressAcceptsLoopback(t *testing.T) {
	for _, address := range []string{
		"tcp://127.0.0.1:26658",
		"tcp://localhost:26658",
		"tcp://[::1]:26658",
	} {
		if err := validateListenAddress(address); err != nil {
			t.Errorf("expected loopback address %q to be accepted: %v", address, err)
		}
	}
}

func TestValidateListenAddressRejectsPublicOrMalformedAddresses(t *testing.T) {
	for _, address := range []string{
		"tcp://0.0.0.0:26658",
		"tcp://192.0.2.10:26658",
		"tcp://[::]:26658",
		"tcp://127.0.0.1",
		"tcp://127.0.0.1:0",
		"http://127.0.0.1:26658",
		"tcp://127.0.0.1:26658/path",
	} {
		if err := validateListenAddress(address); err == nil {
			t.Errorf("expected unsafe or malformed address %q to be rejected", address)
		}
	}
}
