import { useCallback, useEffect, useState } from 'react';
import { Download, KeyRound, Plug, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { Switch } from '@/components/ui/switch';

import {
  ConnectMCPServer,
  DisconnectMCPServer,
  ImportMCPServersFromClaudeConfig,
  ListMCPServers,
  SetMCPServerEnabled,
} from '../../../wailsjs/go/main/App';
import { main } from '../../../wailsjs/go/models';

type MCPServerInfo = main.MCPServerInfo;

/**
 * McpServersSection manages the host's MCP tool-server registry. Servers are
 * defined host-side (with their credentials); here the user enables/disables
 * them and imports from their Claude config. Enabling a server only makes it
 * *available* to expose — each endpoint opts in via its Sandbox dialog. The
 * credential never leaves the host: the egress broker injects it per request.
 */
export function McpServersSection() {
  const [servers, setServers] = useState<MCPServerInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const fetchServers = useCallback(async () => {
    setLoading(true);
    try {
      const result = await ListMCPServers();
      setServers(result || []);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchServers();
  }, [fetchServers]);

  // run wraps every server action in the shared busy/notice/error/refresh
  // protocol; the action returns an optional success notice.
  const run = async (key: string, action: () => Promise<string | void>) => {
    setBusy(key);
    setError('');
    setNotice('');
    try {
      const notice = await action();
      if (notice) setNotice(notice);
      await fetchServers();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(null);
    }
  };

  const toggle = (srv: MCPServerInfo) =>
    run(srv.name, () => SetMCPServerEnabled(srv.name, !srv.enabled));

  const connect = (srv: MCPServerInfo) =>
    // Opens the browser; resolves when the user finishes authorizing.
    run(srv.name, async () => {
      await ConnectMCPServer(srv.name);
      return `Connected ${srv.name}.`;
    });

  const disconnect = (srv: MCPServerInfo) => run(srv.name, () => DisconnectMCPServer(srv.name));

  const importFromClaude = () =>
    run('__import__', async () => {
      const res = await ImportMCPServersFromClaudeConfig();
      const skipped = res.skipped?.length ? ` (skipped ${res.skipped.length})` : '';
      return `Imported ${res.imported} server${res.imported === 1 ? '' : 's'}${skipped}.`;
    });

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <header>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-foreground">MCP Servers</h2>
            {servers.length > 0 && (
              <span className="px-1.5 py-0.5 rounded text-xs bg-muted text-muted-foreground tabular-nums">
                {servers.length}
              </span>
            )}
          </div>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0 text-primary" />
            Brokered by the host — credentials never enter containers.
          </p>
        </header>
        <Button
          size="sm"
          variant="outline"
          onClick={importFromClaude}
          disabled={busy === '__import__'}
          className="h-7 text-xs"
        >
          {busy === '__import__' ? (
            <Spinner className="w-3.5 h-3.5" />
          ) : (
            <Download className="w-3.5 h-3.5" />
          )}
          Import from Claude
        </Button>
      </div>

      {notice && <p className="text-xs text-primary">{notice}</p>}
      {error && <p className="text-xs text-destructive break-words">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-3 justify-center py-8 text-muted-foreground">
          <Spinner className="w-5 h-5 text-primary" />
          <span className="text-sm">Loading servers…</span>
        </div>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center rounded-lg border-2 border-dashed border-border/60 bg-card/30 px-6 py-8">
          <Plug className="w-9 h-9 mb-3 text-muted-foreground" />
          <p className="text-sm text-foreground">No MCP servers configured</p>
          <p className="text-xs text-muted-foreground/70 mt-1 max-w-sm">
            Import the servers from your Claude config, or add them by hand to the host's
            mcp/servers.json. Enable a server here, then expose it to specific endpoints from
            their Sandbox dialog.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {servers.map((srv) => (
            <li
              key={srv.name}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-card/50 border border-border/50"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-foreground truncate">{srv.name}</span>
                  <span className="rounded bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
                    {srv.transport}
                  </span>
                  {srv.source === 'import:claude' && (
                    <span className="rounded bg-secondary/60 px-1 py-0.5 text-[10px] text-muted-foreground/70">
                      from Claude
                    </span>
                  )}
                  {srv.source === 'import:claude-plugin' && (
                    <span className="rounded bg-secondary/60 px-1 py-0.5 text-[10px] text-muted-foreground/70">
                      from plugin
                    </span>
                  )}
                  {srv.authMode === 'oauth' && (
                    <span
                      className={`rounded px-1 py-0.5 text-[10px] ${
                        srv.authStatus === 'connected'
                          ? 'bg-chart-2/20 text-chart-2'
                          : 'bg-chart-3/20 text-chart-3'
                      }`}
                    >
                      {srv.authStatus === 'connected'
                        ? 'connected'
                        : srv.authStatus === 'expired'
                          ? 'reconnect'
                          : 'not connected'}
                    </span>
                  )}
                </div>
              </div>

              {/* Remote servers without a static credential: connect via OAuth
                  (the broker holds the token). Header-credentialed servers skip
                  this — they use their stored PAT. */}
              {srv.transport === 'http' &&
                srv.authMode !== 'header' &&
                (srv.authStatus === 'connected' ? (
                  <button
                    type="button"
                    onClick={() => disconnect(srv)}
                    disabled={busy === srv.name}
                    className="px-2 py-1 rounded text-xs text-muted-foreground hover:text-destructive hover:bg-secondary/60 disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                ) : (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => connect(srv)}
                    disabled={busy === srv.name}
                    className="h-7 text-xs"
                  >
                    {busy === srv.name ? (
                      <Spinner className="w-3.5 h-3.5" />
                    ) : (
                      <KeyRound className="w-3.5 h-3.5" />
                    )}
                    Connect
                  </Button>
                ))}

              <Switch
                checked={srv.enabled}
                disabled={busy === srv.name}
                onCheckedChange={() => toggle(srv)}
                aria-label={srv.enabled ? `Disable ${srv.name}` : `Enable ${srv.name}`}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
