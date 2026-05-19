// Command nats-auth is the SyftHub NATS auth-callout service.
//
// It is the authorization decision point for every NATS connection. The NATS
// server — configured with `authorization { auth_callout { ... } }` — packages
// each connecting client's credentials into a signed request on
// $SYS.REQ.USER.AUTH. This service validates the presented token and replies
// with a signed user JWT scoped to exactly the subjects that client may use:
//
//   - service token  (backend / aggregator): full syfthub.> + JetStream access
//   - host token      (ht_…, Redis nats:host:{tok}): a space serving agent
//     endpoints — subscribes its own space subject, publishes any peer channel
//   - peer token      (pt_…, Redis nats:peer:{tok}): a client dialing a host —
//     publishes the target space subject, subscribes its own peer channel
//
// Tokens are minted by the hub backend; a token this service cannot resolve is
// rejected. See syfthub-desktop/docs/p2p-agent-direct-nats-design.md.
//
// `nats-auth genkey` prints a fresh signing-account seed + public key for the
// NATS_CALLOUT_ACCOUNT_SEED / NATS_CALLOUT_ISSUER configuration pair.
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/nats-io/jwt/v2"
	"github.com/nats-io/nats.go"
	"github.com/nats-io/nkeys"
	"github.com/redis/go-redis/v9"
)

// authRequestSubject is the system subject the NATS server publishes
// auth-callout requests on.
const authRequestSubject = "$SYS.REQ.USER.AUTH"

// jetStreamSubjects are the JetStream API, Object Store, and KV subjects an
// agent host or client needs for the attachment Object Store and session KV.
var jetStreamSubjects = []string{"$JS.API.>", "$O.>", "$KV.>"}

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stderr, nil))

	if len(os.Args) > 1 && os.Args[1] == "genkey" {
		if err := genKey(); err != nil {
			logger.Error("genkey failed", "error", err)
			os.Exit(1)
		}
		return
	}

	if err := run(logger); err != nil {
		logger.Error("nats-auth failed", "error", err)
		os.Exit(1)
	}
}

// genKey prints a fresh account signing keypair for the auth-callout config.
func genKey() error {
	kp, err := nkeys.CreateAccount()
	if err != nil {
		return err
	}
	seed, err := kp.Seed()
	if err != nil {
		return err
	}
	pub, err := kp.PublicKey()
	if err != nil {
		return err
	}
	fmt.Printf("NATS_CALLOUT_ACCOUNT_SEED=%s\nNATS_CALLOUT_ISSUER=%s\n", seed, pub)
	return nil
}

// config is the service configuration, read from the environment.
type config struct {
	natsURL       string
	natsUser      string // AUTH-account user the service connects as (exempt from callout)
	natsPassword  string
	accountSeed   string // SA… seed of the signing account; its public key is the callout `issuer`
	targetAccount string // config account the issued users are placed in (e.g. "SYFTHUB")
	redisURL      string
	serviceToken  string // shared token presented by trusted server components
}

func loadConfig() (*config, error) {
	c := &config{
		natsURL:       env("NATS_URL", "nats://nats:4222"),
		natsUser:      env("NATS_AUTH_SERVICE_USER", "auth_service"),
		natsPassword:  os.Getenv("NATS_AUTH_SERVICE_PASSWORD"),
		accountSeed:   os.Getenv("NATS_CALLOUT_ACCOUNT_SEED"),
		targetAccount: env("NATS_CALLOUT_ACCOUNT", "SYFTHUB"),
		redisURL:      env("REDIS_URL", "redis://redis:6379/0"),
		serviceToken:  os.Getenv("NATS_AUTH_SERVICE_TOKEN"),
	}
	switch {
	case c.natsPassword == "":
		return nil, fmt.Errorf("NATS_AUTH_SERVICE_PASSWORD is required")
	case c.accountSeed == "":
		return nil, fmt.Errorf("NATS_CALLOUT_ACCOUNT_SEED is required (see `nats-auth genkey`)")
	case c.serviceToken == "":
		return nil, fmt.Errorf("NATS_AUTH_SERVICE_TOKEN is required")
	}
	return c, nil
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func run(logger *slog.Logger) error {
	cfg, err := loadConfig()
	if err != nil {
		return err
	}

	accountKP, err := nkeys.FromSeed([]byte(cfg.accountSeed))
	if err != nil {
		return fmt.Errorf("invalid NATS_CALLOUT_ACCOUNT_SEED: %w", err)
	}
	issuer, err := accountKP.PublicKey()
	if err != nil {
		return fmt.Errorf("derive callout account public key: %w", err)
	}
	logger.Info("loaded callout signing account", "issuer", issuer)

	redisOpts, err := redis.ParseURL(cfg.redisURL)
	if err != nil {
		return fmt.Errorf("invalid REDIS_URL: %w", err)
	}
	rdb := redis.NewClient(redisOpts)
	defer rdb.Close()

	nc, err := nats.Connect(cfg.natsURL,
		nats.UserInfo(cfg.natsUser, cfg.natsPassword),
		nats.Name("syfthub-nats-auth"),
		nats.MaxReconnects(-1),
		nats.ReconnectWait(2*time.Second),
	)
	if err != nil {
		return fmt.Errorf("connect to NATS at %s: %w", cfg.natsURL, err)
	}
	defer nc.Close()

	h := &handler{
		auth:      &authorizer{rdb: rdb, serviceToken: cfg.serviceToken},
		accountKP: accountKP,
		account:   cfg.targetAccount,
		logger:    logger,
	}

	sub, err := nc.Subscribe(authRequestSubject, h.handle)
	if err != nil {
		return fmt.Errorf("subscribe to %s: %w", authRequestSubject, err)
	}
	defer func() { _ = sub.Unsubscribe() }()

	logger.Info("nats-auth callout service ready",
		"subject", authRequestSubject, "account", cfg.targetAccount)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	<-ctx.Done()
	logger.Info("nats-auth shutting down")
	return nil
}

// handler builds and signs the auth-callout response for one request.
type handler struct {
	auth      *authorizer
	accountKP nkeys.KeyPair
	account   string
	logger    *slog.Logger
}

// handle answers one auth-callout request: it decodes the request, resolves the
// presented token to a permission set, and replies with a signed user JWT (or
// a signed rejection).
func (h *handler) handle(msg *nats.Msg) {
	arc, err := jwt.DecodeAuthorizationRequestClaims(string(msg.Data))
	if err != nil {
		// Without the request claims there is no UserNkey to address a
		// response to — nothing to do but log.
		h.logger.Error("decode auth request", "error", err)
		return
	}

	rc := jwt.NewAuthorizationResponseClaims(arc.UserNkey)
	rc.Audience = arc.Server.ID

	respond := func() {
		token, encErr := rc.Encode(h.accountKP)
		if encErr != nil {
			h.logger.Error("encode auth response", "error", encErr)
			return
		}
		_ = msg.Respond([]byte(token))
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	p, err := h.auth.authorize(ctx, arc.ConnectOptions.Token)
	if err != nil {
		h.logger.Warn("connection rejected", "error", err, "client", arc.ClientInformation.Name)
		rc.Error = err.Error()
		respond()
		return
	}

	uc := jwt.NewUserClaims(arc.UserNkey)
	uc.Audience = h.account
	uc.User.Pub.Allow = jwt.StringList(p.pub)
	uc.User.Sub.Allow = jwt.StringList(p.sub)
	ujwt, err := uc.Encode(h.accountKP)
	if err != nil {
		h.logger.Error("encode user claims", "error", err)
		rc.Error = "internal authorization error"
		respond()
		return
	}
	rc.Jwt = ujwt
	respond()
	h.logger.Info("connection authorized",
		"client", arc.ClientInformation.Name, "kind", p.kind,
		"pub_subjects", len(p.pub), "sub_subjects", len(p.sub))
}

// authorizer resolves a presented token into a NATS permission set.
type authorizer struct {
	rdb          *redis.Client
	serviceToken string
}

// peerTokenRecord mirrors the JSON the hub backend stores at nats:peer:{token}.
type peerTokenRecord struct {
	PeerChannel     string   `json:"peer_channel"`
	TargetUsernames []string `json:"target_usernames"`
}

// hostTokenRecord mirrors the JSON the hub backend stores at nats:host:{token}.
type hostTokenRecord struct {
	Username string `json:"username"`
}

// perms is a resolved permission set for one connection.
type perms struct {
	kind string
	pub  []string
	sub  []string
}

// authorize classifies token and returns the subjects it may publish to and
// subscribe to, or an error if the token is unknown.
func (a *authorizer) authorize(ctx context.Context, token string) (*perms, error) {
	switch {
	case token == "":
		return nil, fmt.Errorf("no token presented")

	case token == a.serviceToken:
		// Trusted server components (backend, aggregator) — full access.
		return &perms{kind: "service", pub: []string{">"}, sub: []string{">"}}, nil

	case strings.HasPrefix(token, "pt_"):
		var rec peerTokenRecord
		if err := a.lookup(ctx, "nats:peer:"+token, &rec); err != nil {
			return nil, fmt.Errorf("unknown or expired peer token")
		}
		p := &perms{
			kind: "peer",
			pub:  append([]string{"_INBOX.>"}, jetStreamSubjects...),
			sub:  append([]string{"_INBOX.>", "syfthub.peer." + rec.PeerChannel}, jetStreamSubjects...),
		}
		for _, u := range rec.TargetUsernames {
			p.pub = append(p.pub, "syfthub.spaces."+u)
		}
		return p, nil

	case strings.HasPrefix(token, "ht_"):
		var rec hostTokenRecord
		if err := a.lookup(ctx, "nats:host:"+token, &rec); err != nil {
			return nil, fmt.Errorf("unknown or expired host token")
		}
		// A desktop is a symmetric peer: one connection serves both the host
		// role (subscribe its own space, reply to any client's peer channel)
		// and the client role (publish to any space it dials, subscribe its
		// own namespaced peer channels). Publish is broad — harmless: every
		// space is gated by tunnel encryption + satellite-token verification.
		// Subscribe is tightly scoped to the space's own inbox and peer
		// namespace, so a host can never read another peer's traffic.
		return &perms{
			kind: "host",
			pub: append([]string{"_INBOX.>", "syfthub.peer.>", "syfthub.spaces.>"},
				jetStreamSubjects...),
			sub: append([]string{
				"_INBOX.>",
				"syfthub.spaces." + rec.Username,
				"syfthub.peer." + rec.Username + ".>",
			}, jetStreamSubjects...),
		}, nil

	default:
		return nil, fmt.Errorf("unrecognized token")
	}
}

// lookup reads key from Redis and JSON-decodes it into out.
func (a *authorizer) lookup(ctx context.Context, key string, out any) error {
	raw, err := a.rdb.Get(ctx, key).Bytes()
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, out)
}
