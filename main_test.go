// SPDX-License-Identifier: MIT
package main

import (
	"encoding/json"
	"testing"
)

func decodeInterceptResponse(t *testing.T, raw []byte) interceptResponse {
	t.Helper()
	var env envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatal(err)
	}
	if !env.OK || env.Error != nil {
		t.Fatalf("unexpected envelope: %s", raw)
	}
	var response interceptResponse
	if err := json.Unmarshal(env.Result, &response); err != nil {
		t.Fatal(err)
	}
	return response
}

func interceptFixture(t *testing.T, method string, headers map[string][]string) interceptResponse {
	t.Helper()
	payload, err := json.Marshal(interceptRequest{RequestID: "request-1", Headers: headers})
	if err != nil {
		t.Fatal(err)
	}
	raw, err := handleMethod(method, payload)
	if err != nil {
		t.Fatal(err)
	}
	return decodeInterceptResponse(t, raw)
}

func TestInterceptMapsSessionHeaderForBothHooks(t *testing.T) {
	for _, method := range []string{"request.intercept_before", "request.intercept_after"} {
		t.Run(method, func(t *testing.T) {
			response := interceptFixture(t, method, map[string][]string{
				"x-deepseek-harness-session-id": {"  session-123  ", "ignored"},
			})
			values := response.Headers[targetHeader]
			if len(values) != 1 || values[0] != "session-123" {
				t.Fatalf("headers = %#v, want mapped session", response.Headers)
			}
			if len(response.ClearHeaders) != 0 {
				t.Fatalf("clear headers = %#v, want empty", response.ClearHeaders)
			}
		})
	}
}

func TestInterceptPreservesExistingTargetHeader(t *testing.T) {
	for _, targetName := range []string{targetHeader, "x-session-id"} {
		response := interceptFixture(t, "request.intercept_after", map[string][]string{
			sourceHeader: {"source-session"},
			targetName:   {"existing-session"},
		})
		if len(response.Headers) != 0 {
			t.Fatalf("target %q was overwritten: %#v", targetName, response.Headers)
		}
	}
}

func TestInterceptSkipsMissingOrBlankSource(t *testing.T) {
	cases := []map[string][]string{
		nil,
		{},
		{sourceHeader: nil},
		{sourceHeader: {}},
		{sourceHeader: {"  "}},
		{"unrelated": {"session-123"}},
	}
	for index, headers := range cases {
		response := interceptFixture(t, "request.intercept_before", headers)
		if len(response.Headers) != 0 {
			t.Fatalf("case %d headers = %#v, want no-op", index, response.Headers)
		}
	}
}

func TestInterceptRejectsMalformedOuterPayload(t *testing.T) {
	if _, err := interceptHeaders([]byte(`{"Headers":`)); err == nil {
		t.Fatal("malformed interceptor payload was accepted")
	}
}

func TestRegisterIdentityAndCapabilities(t *testing.T) {
	raw, err := handleMethod("plugin.register", nil)
	if err != nil {
		t.Fatal(err)
	}
	var env envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatal(err)
	}
	if !env.OK {
		t.Fatalf("registration failed: %s", raw)
	}
	var reg registration
	if err := json.Unmarshal(env.Result, &reg); err != nil {
		t.Fatal(err)
	}
	if reg.SchemaVersion != abiVersion {
		t.Errorf("schema version = %d, want %d", reg.SchemaVersion, abiVersion)
	}
	if !reg.Capabilities.RequestInterceptor {
		t.Error("request_interceptor = false, want true")
	}
	if reg.Metadata.Name != pluginID ||
		reg.Metadata.Version != pluginVersion ||
		reg.Metadata.Author != "ahoo" ||
		reg.Metadata.GitHubRepository != "https://github.com/ahoo/cpa-plugin-deepseek-harness-session" ||
		reg.Metadata.Logo != "" ||
		len(reg.Metadata.ConfigFields) != 0 {
		t.Errorf("metadata = %+v, want exact v0.1.2 identity", reg.Metadata)
	}
}

func TestRequestLengthSupported(t *testing.T) {
	if !requestLengthSupported(maxCGoBytesLength) {
		t.Fatal("maximum C.GoBytes request length should be accepted")
	}
	if requestLengthSupported(maxCGoBytesLength + 1) {
		t.Fatal("oversized request length should be rejected")
	}
}

func TestProcessPluginCallReturnsFailureEnvelope(t *testing.T) {
	raw, status := processPluginCall("request.intercept_after", []byte(`{"Headers":`))
	if status != 1 {
		t.Fatalf("status = %d, want 1", status)
	}
	var env envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatal(err)
	}
	if env.OK || env.Error == nil || env.Error.Code != "plugin_error" {
		t.Fatalf("envelope = %+v, want plugin_error", env)
	}
}
