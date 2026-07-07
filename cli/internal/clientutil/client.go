// Package clientutil centralizes construction of the syfthub.Client used by
// the CLI, so that config-to-option translation lives in exactly one place.
package clientutil

import (
	"time"

	"github.com/OpenMined/syfthub/cli/internal/nodeconfig"
	"github.com/openmined/syfthub/sdk/golang/syfthub"
)

// NewClient builds a *syfthub.Client from the given NodeConfig.
//
// If aggregatorAlias is non-empty, the resolved aggregator URL
// (cfg.GetAggregatorURL(aggregatorAlias)) is applied when non-empty.
// If timeoutOverride > 0, it is used in place of cfg.TimeoutDuration().
// Any extra options are appended last and therefore take precedence over
// the config-derived ones.
func NewClient(cfg *nodeconfig.NodeConfig, aggregatorAlias string, timeoutOverride time.Duration, extra ...syfthub.Option) (*syfthub.Client, error) {
	opts := []syfthub.Option{
		syfthub.WithBaseURL(cfg.HubURL),
	}

	timeout := timeoutOverride
	if timeout <= 0 {
		timeout = cfg.TimeoutDuration()
	}
	opts = append(opts, syfthub.WithTimeout(timeout))

	if cfg.HasAPIToken() {
		opts = append(opts, syfthub.WithAPIToken(cfg.APIToken))
	}

	if aggregatorAlias != "" {
		if url := cfg.GetAggregatorURL(aggregatorAlias); url != "" {
			opts = append(opts, syfthub.WithAggregatorURL(url))
		}
	}

	opts = append(opts, extra...)

	return syfthub.NewClient(opts...)
}
