package syfthubapi

import (
	"context"
	"encoding/json"
)

// EndpointCodec handles type-specific serialization for an endpoint type.
// This is the minimal surface that differs between model and data_source endpoints.
type EndpointCodec interface {
	ParsePayload(payload json.RawMessage) (any, error)
	WrapResponse(result any) (any, error)
	EnrichLog(log *RequestLog, payload json.RawMessage)
	SetExecutorFields(input *ExecutorInput, parsed any)
	UnmarshalResult(raw json.RawMessage) (any, error)
}

// ModelCodec handles model endpoint serialization.
type ModelCodec struct{}

func (ModelCodec) ParsePayload(payload json.RawMessage) (any, error) {
	var req ModelQueryRequest
	if err := json.Unmarshal(payload, &req); err != nil {
		return nil, errInvalidPayload(err)
	}
	return req.Messages, nil
}

func (ModelCodec) WrapResponse(result any) (any, error) {
	response := result.(string)
	return ModelQueryResponse{
		Summary: ModelSummary{
			Message: ModelSummaryMessage{Content: response},
		},
	}, nil
}

func (ModelCodec) EnrichLog(log *RequestLog, payload json.RawMessage) {
	if log.Request == nil {
		return
	}
	var req ModelQueryRequest
	if err := json.Unmarshal(payload, &req); err == nil {
		log.Request.Messages = req.Messages
	}
}

func (ModelCodec) SetExecutorFields(input *ExecutorInput, parsed any) {
	input.Messages = parsed.([]Message)
}

func (ModelCodec) UnmarshalResult(raw json.RawMessage) (any, error) {
	var s string
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, err
	}
	return s, nil
}

// DataSourceCodec handles data source endpoint serialization.
type DataSourceCodec struct{}

func (DataSourceCodec) ParsePayload(payload json.RawMessage) (any, error) {
	var req DataSourceQueryRequest
	if err := json.Unmarshal(payload, &req); err != nil {
		return nil, errInvalidPayload(err)
	}
	return req.GetQuery(), nil
}

func (DataSourceCodec) WrapResponse(result any) (any, error) {
	docs := result.([]Document)
	return DataSourceQueryResponse{
		References: DataSourceReferences{Documents: docs},
	}, nil
}

func (DataSourceCodec) EnrichLog(log *RequestLog, payload json.RawMessage) {
	if log.Request == nil {
		return
	}
	var req DataSourceQueryRequest
	if err := json.Unmarshal(payload, &req); err == nil {
		log.Request.Query = req.GetQuery()
	}
}

func (DataSourceCodec) SetExecutorFields(input *ExecutorInput, parsed any) {
	input.Query = parsed.(string)
}

func (DataSourceCodec) UnmarshalResult(raw json.RawMessage) (any, error) {
	var docs []Document
	if err := json.Unmarshal(raw, &docs); err != nil {
		return nil, err
	}
	return docs, nil
}

// UnifiedInvoker handles endpoint invocation for any type through a codec.
// It replaces the separate ModelInvoker and DataSourceInvoker.
type UnifiedInvoker struct {
	codec    EndpointCodec
	handler  func(ctx context.Context, input any, reqCtx *RequestContext) (any, error)
	executor Executor
	slug     string
	epType   EndpointType
}

func (u *UnifiedInvoker) ParseRequest(payload json.RawMessage) (any, error) {
	return u.codec.ParsePayload(payload)
}

func (u *UnifiedInvoker) Invoke(ctx context.Context, input any, reqCtx *RequestContext) (any, error) {
	if u.executor != nil {
		return u.executeViaSubprocess(ctx, input, reqCtx)
	}
	if u.handler == nil {
		return nil, errNoHandler(u.slug)
	}
	return u.handler(ctx, input, reqCtx)
}

func (u *UnifiedInvoker) FormatResponse(result any) (any, error) {
	return u.codec.WrapResponse(result)
}

func (u *UnifiedInvoker) EnrichLog(log *RequestLog, payload json.RawMessage) {
	u.codec.EnrichLog(log, payload)
}

func (u *UnifiedInvoker) Close() error {
	if u.executor != nil {
		return u.executor.Close()
	}
	return nil
}

func (u *UnifiedInvoker) executeViaSubprocess(ctx context.Context, input any, reqCtx *RequestContext) (any, error) {
	execInput := buildExecutorInput(string(u.epType), u.slug, u.epType, reqCtx)
	u.codec.SetExecutorFields(execInput, input)

	raw, err := executeViaExecutor(ctx, u.executor, execInput, reqCtx, u.slug)
	if err != nil {
		return nil, err
	}

	result, err := u.codec.UnmarshalResult(raw)
	if err != nil {
		return nil, &ExecutionError{
			Endpoint: u.slug,
			Message:  "failed to parse handler result",
			Cause:    err,
		}
	}
	return result, nil
}

// Ensure UnifiedInvoker implements the interface at compile time.
var _ EndpointInvoker = (*UnifiedInvoker)(nil)
