interface TokenRow {
  name: string;
  scope: string;
  queries: string;
  status: "active" | "expired" | "revoked";
  expires: string;
}

interface DashboardMockProps {
  tokens: TokenRow[];
}

const statusColors = {
  active: "bg-emerald-100 text-emerald-700",
  expired: "bg-gray-100 text-gray-500",
  revoked: "bg-red-100 text-red-600",
};

export function DashboardMock({ tokens }: DashboardMockProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-950 shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-sm font-medium text-gray-300">Access Tokens</span>
        </div>
        <button className="rounded-md bg-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-400">
          + Generate Link
        </button>
      </div>
      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
              <th className="px-5 py-3 font-medium">Client</th>
              <th className="px-5 py-3 font-medium">Scope</th>
              <th className="px-5 py-3 font-medium">Queries</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Expires</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((token, i) => (
              <tr key={i} className="border-b border-gray-800/50 last:border-0">
                <td className="px-5 py-3 font-medium text-gray-200">{token.name}</td>
                <td className="px-5 py-3 font-mono text-xs text-gray-400">{token.scope}</td>
                <td className="px-5 py-3 text-gray-300">{token.queries}</td>
                <td className="px-5 py-3">
                  <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[token.status]}`}>
                    {token.status}
                  </span>
                </td>
                <td className="px-5 py-3 text-gray-500">{token.expires}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
