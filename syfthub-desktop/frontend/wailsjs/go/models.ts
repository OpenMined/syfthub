export namespace main {

	export class AccountingConfig {
	    url: string;

	    static createFrom(source: any = {}) {
	        return new AccountingConfig(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.url = source["url"];
	    }
	}
	export class AggregatorConfig {
	    url: string;

	    static createFrom(source: any = {}) {
	        return new AggregatorConfig(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.url = source["url"];
	    }
	}
	export class AttachmentSummary {
	    file_id: string;
	    name: string;
	    mime: string;
	    size_bytes: number;
	    sha256: string;

	    static createFrom(source: any = {}) {
	        return new AttachmentSummary(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.file_id = source["file_id"];
	        this.name = source["name"];
	        this.mime = source["mime"];
	        this.size_bytes = source["size_bytes"];
	        this.sha256 = source["sha256"];
	    }
	}
	export class ChatEndpointRef {
	    url: string;
	    slug: string;
	    name: string;
	    tenant_name?: string;
	    owner_username?: string;

	    static createFrom(source: any = {}) {
	        return new ChatEndpointRef(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.url = source["url"];
	        this.slug = source["slug"];
	        this.name = source["name"];
	        this.tenant_name = source["tenant_name"];
	        this.owner_username = source["owner_username"];
	    }
	}
	export class ChatMessage {
	    role: string;
	    content: string;

	    static createFrom(source: any = {}) {
	        return new ChatMessage(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.role = source["role"];
	        this.content = source["content"];
	    }
	}
	export class ChatRequest {
	    prompt: string;
	    model: ChatEndpointRef;
	    dataSources: ChatEndpointRef[];
	    messages?: ChatMessage[];
	    topK?: number;
	    maxTokens?: number;
	    temperature?: number;

	    static createFrom(source: any = {}) {
	        return new ChatRequest(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.prompt = source["prompt"];
	        this.model = this.convertValues(source["model"], ChatEndpointRef);
	        this.dataSources = this.convertValues(source["dataSources"], ChatEndpointRef);
	        this.messages = this.convertValues(source["messages"], ChatMessage);
	        this.topK = source["topK"];
	        this.maxTokens = source["maxTokens"];
	        this.temperature = source["temperature"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class ConfigInfo {
	    syfthubUrl: string;
	    spaceUrl: string;
	    endpointsPath: string;
	    logLevel: string;
	    watchEnabled: boolean;
	    useEmbeddedPython: boolean;
	    pythonPath?: string;
	    aggregatorUrl?: string;
	    containerEnabled: boolean;

	    static createFrom(source: any = {}) {
	        return new ConfigInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.syfthubUrl = source["syfthubUrl"];
	        this.spaceUrl = source["spaceUrl"];
	        this.endpointsPath = source["endpointsPath"];
	        this.logLevel = source["logLevel"];
	        this.watchEnabled = source["watchEnabled"];
	        this.useEmbeddedPython = source["useEmbeddedPython"];
	        this.pythonPath = source["pythonPath"];
	        this.aggregatorUrl = source["aggregatorUrl"];
	        this.containerEnabled = source["containerEnabled"];
	    }
	}
	export class CreateEndpointRequest {
	    name: string;
	    type: string;
	    description: string;
	    version: string;

	    static createFrom(source: any = {}) {
	        return new CreateEndpointRequest(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.type = source["type"];
	        this.description = source["description"];
	        this.version = source["version"];
	    }
	}
	export class Dependency {
	    package: string;
	    version: string;

	    static createFrom(source: any = {}) {
	        return new Dependency(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.package = source["package"];
	        this.version = source["version"];
	    }
	}
	export class SetupStepInfo {
	    id: string;
	    name: string;
	    description?: string;
	    type: string;
	    required: boolean;
	    status: string;
	    expiresAt?: string;

	    static createFrom(source: any = {}) {
	        return new SetupStepInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.name = source["name"];
	        this.description = source["description"];
	        this.type = source["type"];
	        this.required = source["required"];
	        this.status = source["status"];
	        this.expiresAt = source["expiresAt"];
	    }
	}
	export class SetupSpecInfo {
	    version: string;
	    steps: SetupStepInfo[];

	    static createFrom(source: any = {}) {
	        return new SetupSpecInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.version = source["version"];
	        this.steps = this.convertValues(source["steps"], SetupStepInfo);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class SetupStatusInfo {
	    isComplete: boolean;
	    totalSteps: number;
	    completed: number;
	    pendingSteps: string[];
	    expiredSteps: string[];

	    static createFrom(source: any = {}) {
	        return new SetupStatusInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.isComplete = source["isComplete"];
	        this.totalSteps = source["totalSteps"];
	        this.completed = source["completed"];
	        this.pendingSteps = source["pendingSteps"];
	        this.expiredSteps = source["expiredSteps"];
	    }
	}
	export class Policy {
	    name: string;
	    type: string;
	    config: Record<string, any>;

	    static createFrom(source: any = {}) {
	        return new Policy(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.type = source["type"];
	        this.config = source["config"];
	    }
	}
	export class EndpointDetail {
	    slug: string;
	    name: string;
	    description: string;
	    type: string;
	    version: string;
	    enabled: boolean;
	    hasReadme: boolean;
	    hasPolicies: boolean;
	    depsCount: number;
	    envCount: number;
	    runnerCode: string;
	    readmeContent: string;
	    policies: Policy[];
	    setupStatus?: SetupStatusInfo;
	    setupSpec?: SetupSpecInfo;

	    static createFrom(source: any = {}) {
	        return new EndpointDetail(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.slug = source["slug"];
	        this.name = source["name"];
	        this.description = source["description"];
	        this.type = source["type"];
	        this.version = source["version"];
	        this.enabled = source["enabled"];
	        this.hasReadme = source["hasReadme"];
	        this.hasPolicies = source["hasPolicies"];
	        this.depsCount = source["depsCount"];
	        this.envCount = source["envCount"];
	        this.runnerCode = source["runnerCode"];
	        this.readmeContent = source["readmeContent"];
	        this.policies = this.convertValues(source["policies"], Policy);
	        this.setupStatus = this.convertValues(source["setupStatus"], SetupStatusInfo);
	        this.setupSpec = this.convertValues(source["setupSpec"], SetupSpecInfo);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class EndpointInfo {
	    slug: string;
	    name: string;
	    description: string;
	    type: string;
	    enabled: boolean;
	    version?: string;
	    hasPolicies: boolean;
	    setupStatus?: SetupStatusInfo;
	    runtimeState?: string;

	    static createFrom(source: any = {}) {
	        return new EndpointInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.slug = source["slug"];
	        this.name = source["name"];
	        this.description = source["description"];
	        this.type = source["type"];
	        this.enabled = source["enabled"];
	        this.version = source["version"];
	        this.hasPolicies = source["hasPolicies"];
	        this.setupStatus = this.convertValues(source["setupStatus"], SetupStatusInfo);
	        this.runtimeState = source["runtimeState"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class EnvVar {
	    key: string;
	    value: string;

	    static createFrom(source: any = {}) {
	        return new EnvVar(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.key = source["key"];
	        this.value = source["value"];
	    }
	}
	export class FundResult {
	    address: string;
	    hashes: string[];
	    network: string;
	    faucet_url: string;

	    static createFrom(source: any = {}) {
	        return new FundResult(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.address = source["address"];
	        this.hashes = source["hashes"];
	        this.network = source["network"];
	        this.faucet_url = source["faucet_url"];
	    }
	}
	export class PackageConfigField {
	    key: string;
	    label: string;
	    description?: string;
	    required: boolean;
	    secret: boolean;
	    default?: string;

	    static createFrom(source: any = {}) {
	        return new PackageConfigField(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.key = source["key"];
	        this.label = source["label"];
	        this.description = source["description"];
	        this.required = source["required"];
	        this.secret = source["secret"];
	        this.default = source["default"];
	    }
	}
	export class LibraryPackage {
	    slug: string;
	    name: string;
	    description: string;
	    type: string;
	    author?: string;
	    version: string;
	    downloadUrl: string;
	    tags?: string[];
	    config?: PackageConfigField[];

	    static createFrom(source: any = {}) {
	        return new LibraryPackage(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.slug = source["slug"];
	        this.name = source["name"];
	        this.description = source["description"];
	        this.type = source["type"];
	        this.author = source["author"];
	        this.version = source["version"];
	        this.downloadUrl = source["downloadUrl"];
	        this.tags = source["tags"];
	        this.config = this.convertValues(source["config"], PackageConfigField);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class LogPolicyInfo {
	    evaluated: boolean;
	    allowed: boolean;
	    policyName?: string;
	    reason?: string;
	    pending?: boolean;

	    static createFrom(source: any = {}) {
	        return new LogPolicyInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.evaluated = source["evaluated"];
	        this.allowed = source["allowed"];
	        this.policyName = source["policyName"];
	        this.reason = source["reason"];
	        this.pending = source["pending"];
	    }
	}
	export class LogTimingInfo {
	    receivedAt: string;
	    processedAt: string;
	    durationMs: number;

	    static createFrom(source: any = {}) {
	        return new LogTimingInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.receivedAt = source["receivedAt"];
	        this.processedAt = source["processedAt"];
	        this.durationMs = source["durationMs"];
	    }
	}
	export class LogResponseInfo {
	    success: boolean;
	    content?: string;
	    contentTruncated?: boolean;
	    error?: string;
	    errorType?: string;
	    errorCode?: string;

	    static createFrom(source: any = {}) {
	        return new LogResponseInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.success = source["success"];
	        this.content = source["content"];
	        this.contentTruncated = source["contentTruncated"];
	        this.error = source["error"];
	        this.errorType = source["errorType"];
	        this.errorCode = source["errorCode"];
	    }
	}
	export class LogRequestInfo {
	    type: string;
	    messages?: ChatMessage[];
	    query?: string;
	    rawSize: number;

	    static createFrom(source: any = {}) {
	        return new LogRequestInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.type = source["type"];
	        this.messages = this.convertValues(source["messages"], ChatMessage);
	        this.query = source["query"];
	        this.rawSize = source["rawSize"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class LogUserInfo {
	    id: string;
	    username?: string;
	    email?: string;
	    role?: string;

	    static createFrom(source: any = {}) {
	        return new LogUserInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.username = source["username"];
	        this.email = source["email"];
	        this.role = source["role"];
	    }
	}
	export class RequestLogEntry {
	    id: string;
	    timestamp: string;
	    correlationId: string;
	    endpointSlug: string;
	    endpointType: string;
	    status?: string;
	    user?: LogUserInfo;
	    request?: LogRequestInfo;
	    response?: LogResponseInfo;
	    policy?: LogPolicyInfo;
	    timing?: LogTimingInfo;

	    static createFrom(source: any = {}) {
	        return new RequestLogEntry(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.timestamp = source["timestamp"];
	        this.correlationId = source["correlationId"];
	        this.endpointSlug = source["endpointSlug"];
	        this.endpointType = source["endpointType"];
	        this.status = source["status"];
	        this.user = this.convertValues(source["user"], LogUserInfo);
	        this.request = this.convertValues(source["request"], LogRequestInfo);
	        this.response = this.convertValues(source["response"], LogResponseInfo);
	        this.policy = this.convertValues(source["policy"], LogPolicyInfo);
	        this.timing = this.convertValues(source["timing"], LogTimingInfo);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class LogQueryResult {
	    logs: RequestLogEntry[];
	    total: number;
	    hasMore: boolean;

	    static createFrom(source: any = {}) {
	        return new LogQueryResult(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.logs = this.convertValues(source["logs"], RequestLogEntry);
	        this.total = source["total"];
	        this.hasMore = source["hasMore"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}


	export class LogStats {
	    totalRequests: number;
	    successCount: number;
	    errorCount: number;
	    policyDenyCount: number;
	    avgDurationMs: number;
	    lastRequestTime?: string;

	    static createFrom(source: any = {}) {
	        return new LogStats(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.totalRequests = source["totalRequests"];
	        this.successCount = source["successCount"];
	        this.errorCount = source["errorCount"];
	        this.policyDenyCount = source["policyDenyCount"];
	        this.avgDurationMs = source["avgDurationMs"];
	        this.lastRequestTime = source["lastRequestTime"];
	    }
	}


	export class MCPImportResult {
	    imported: number;
	    skipped: string[];

	    static createFrom(source: any = {}) {
	        return new MCPImportResult(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.imported = source["imported"];
	        this.skipped = source["skipped"];
	    }
	}
	export class MCPServerInfo {
	    name: string;
	    transport: string;
	    enabled: boolean;
	    source: string;
	    authMode: string;
	    authStatus: string;

	    static createFrom(source: any = {}) {
	        return new MCPServerInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.transport = source["transport"];
	        this.enabled = source["enabled"];
	        this.source = source["source"];
	        this.authMode = source["authMode"];
	        this.authStatus = source["authStatus"];
	    }
	}
	export class ManualReviewEntry {
	    reviewId: string;
	    policyName: string;
	    userId: string;
	    status: string;
	    rejectReason?: string;
	    createdAt: string;
	    resolvedAt?: string;
	    requestType?: string;
	    requestText?: string;
	    requestMessages?: ChatMessage[];
	    responseText?: string;

	    static createFrom(source: any = {}) {
	        return new ManualReviewEntry(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.reviewId = source["reviewId"];
	        this.policyName = source["policyName"];
	        this.userId = source["userId"];
	        this.status = source["status"];
	        this.rejectReason = source["rejectReason"];
	        this.createdAt = source["createdAt"];
	        this.resolvedAt = source["resolvedAt"];
	        this.requestType = source["requestType"];
	        this.requestText = source["requestText"];
	        this.requestMessages = this.convertValues(source["requestMessages"], ChatMessage);
	        this.responseText = source["responseText"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class MountEntry {
	    source: string;
	    target: string;
	    readOnly: boolean;
	    isDir: boolean;

	    static createFrom(source: any = {}) {
	        return new MountEntry(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.source = source["source"];
	        this.target = source["target"];
	        this.readOnly = source["readOnly"];
	        this.isDir = source["isDir"];
	    }
	}
	export class NetworkAgentInfo {
	    slug: string;
	    name: string;
	    description: string;
	    ownerUsername: string;
	    version?: string;
	    tags?: string[];
	    starsCount: number;
	    updatedAt?: string;

	    static createFrom(source: any = {}) {
	        return new NetworkAgentInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.slug = source["slug"];
	        this.name = source["name"];
	        this.description = source["description"];
	        this.ownerUsername = source["ownerUsername"];
	        this.version = source["version"];
	        this.tags = source["tags"];
	        this.starsCount = source["starsCount"];
	        this.updatedAt = source["updatedAt"];
	    }
	}
	export class X402PolicyConfig {
	    price?: string;
	    currency?: string;
	    decimals?: number;
	    chainId?: number;
	    realm?: string;
	    hmacSecretKid?: string;
	    challengeTtlSeconds?: number;
	    maxPendingSettlementsPerPayer?: number;
	    allowListedPayers?: string[];

	    static createFrom(source: any = {}) {
	        return new X402PolicyConfig(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.price = source["price"];
	        this.currency = source["currency"];
	        this.decimals = source["decimals"];
	        this.chainId = source["chainId"];
	        this.realm = source["realm"];
	        this.hmacSecretKid = source["hmacSecretKid"];
	        this.challengeTtlSeconds = source["challengeTtlSeconds"];
	        this.maxPendingSettlementsPerPayer = source["maxPendingSettlementsPerPayer"];
	        this.allowListedPayers = source["allowListedPayers"];
	    }
	}
	export class NewPolicyRequest {
	    name: string;
	    type: string;
	    childPolicies: string[];
	    denyReason: string;
	    x402?: X402PolicyConfig;

	    static createFrom(source: any = {}) {
	        return new NewPolicyRequest(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.type = source["type"];
	        this.childPolicies = source["childPolicies"];
	        this.denyReason = source["denyReason"];
	        this.x402 = this.convertValues(source["x402"], X402PolicyConfig);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

	export class PaymentCap {
	    endpoint_slug: string;
	    soft_cap: string;
	    hard_cap: string;
	    currency: string;
	    updated_at: number;

	    static createFrom(source: any = {}) {
	        return new PaymentCap(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.endpoint_slug = source["endpoint_slug"];
	        this.soft_cap = source["soft_cap"];
	        this.hard_cap = source["hard_cap"];
	        this.currency = source["currency"];
	        this.updated_at = source["updated_at"];
	    }
	}
	export class PaymentCapsConfig {
	    defaults: PaymentCap;
	    per_endpoint: Record<string, PaymentCap>;

	    static createFrom(source: any = {}) {
	        return new PaymentCapsConfig(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.defaults = this.convertValues(source["defaults"], PaymentCap);
	        this.per_endpoint = this.convertValues(source["per_endpoint"], PaymentCap, true);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class PaymentDecision {
	    action: string;
	    effective_cap: PaymentCap;
	    reason?: string;

	    static createFrom(source: any = {}) {
	        return new PaymentDecision(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.action = source["action"];
	        this.effective_cap = this.convertValues(source["effective_cap"], PaymentCap);
	        this.reason = source["reason"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class PaymentRecord {
	    id: string;
	    timestamp_unix: number;
	    endpoint_owner: string;
	    endpoint_slug: string;
	    endpoint_label?: string;
	    amount: string;
	    currency: string;
	    chain_id: number;
	    challenge_id: string;
	    credential_hex: string;
	    tx_hash?: string;
	    status: string;
	    failure_reason?: string;
	    request_summary?: string;
	    settled_unix?: number;

	    static createFrom(source: any = {}) {
	        return new PaymentRecord(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.timestamp_unix = source["timestamp_unix"];
	        this.endpoint_owner = source["endpoint_owner"];
	        this.endpoint_slug = source["endpoint_slug"];
	        this.endpoint_label = source["endpoint_label"];
	        this.amount = source["amount"];
	        this.currency = source["currency"];
	        this.chain_id = source["chain_id"];
	        this.challenge_id = source["challenge_id"];
	        this.credential_hex = source["credential_hex"];
	        this.tx_hash = source["tx_hash"];
	        this.status = source["status"];
	        this.failure_reason = source["failure_reason"];
	        this.request_summary = source["request_summary"];
	        this.settled_unix = source["settled_unix"];
	    }
	}
	export class PaymentTotals {
	    spent_lifetime: string;
	    spent_month: string;
	    spent_session: string;

	    static createFrom(source: any = {}) {
	        return new PaymentTotals(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.spent_lifetime = source["spent_lifetime"];
	        this.spent_month = source["spent_month"];
	        this.spent_session = source["spent_session"];
	    }
	}

	export class PolicyFileInfo {
	    filename: string;
	    name: string;
	    type: string;

	    static createFrom(source: any = {}) {
	        return new PolicyFileInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.filename = source["filename"];
	        this.name = source["name"];
	        this.type = source["type"];
	    }
	}

	export class SandboxSettings {
	    exposeEnv: string[];
	    exposeResources: string[];
	    exposeMcp: string[];
	    workspaceScope: string;
	    workspacePath: string;
	    cpuCores: number;
	    memoryMb: number;
	    timeoutSeconds: number;
	    tmpfsMb: number;

	    static createFrom(source: any = {}) {
	        return new SandboxSettings(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.exposeEnv = source["exposeEnv"];
	        this.exposeResources = source["exposeResources"];
	        this.exposeMcp = source["exposeMcp"];
	        this.workspaceScope = source["workspaceScope"];
	        this.workspacePath = source["workspacePath"];
	        this.cpuCores = source["cpuCores"];
	        this.memoryMb = source["memoryMb"];
	        this.timeoutSeconds = source["timeoutSeconds"];
	        this.tmpfsMb = source["tmpfsMb"];
	    }
	}
	export class SentReviewEntry {
	    reviewId: string;
	    identity: string;
	    endpointPath: string;
	    endpointOwner: string;
	    endpointSlug: string;
	    endpointName: string;
	    endpointType: string;
	    policyName?: string;
	    requestMessages?: ChatMessage[];
	    placeholder?: string;
	    submittedAt: string;
	    status: string;
	    statusSource: string;
	    resolvedAt?: string;
	    rejectReason?: string;
	    responseText?: string;
	    userNote?: string;
	    hostResolvedAt?: string;
	    deliverySeq?: number;
	    parentReviewId?: string;

	    static createFrom(source: any = {}) {
	        return new SentReviewEntry(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.reviewId = source["reviewId"];
	        this.identity = source["identity"];
	        this.endpointPath = source["endpointPath"];
	        this.endpointOwner = source["endpointOwner"];
	        this.endpointSlug = source["endpointSlug"];
	        this.endpointName = source["endpointName"];
	        this.endpointType = source["endpointType"];
	        this.policyName = source["policyName"];
	        this.requestMessages = this.convertValues(source["requestMessages"], ChatMessage);
	        this.placeholder = source["placeholder"];
	        this.submittedAt = source["submittedAt"];
	        this.status = source["status"];
	        this.statusSource = source["statusSource"];
	        this.resolvedAt = source["resolvedAt"];
	        this.rejectReason = source["rejectReason"];
	        this.responseText = source["responseText"];
	        this.userNote = source["userNote"];
	        this.hostResolvedAt = source["hostResolvedAt"];
	        this.deliverySeq = source["deliverySeq"];
	        this.parentReviewId = source["parentReviewId"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class SentReviewInput {
	    reviewId: string;
	    endpointPath: string;
	    endpointName: string;
	    endpointType: string;
	    policyName: string;
	    requestMessages: ChatMessage[];
	    placeholder: string;
	    originReviewId?: string;

	    static createFrom(source: any = {}) {
	        return new SentReviewInput(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.reviewId = source["reviewId"];
	        this.endpointPath = source["endpointPath"];
	        this.endpointName = source["endpointName"];
	        this.endpointType = source["endpointType"];
	        this.policyName = source["policyName"];
	        this.requestMessages = this.convertValues(source["requestMessages"], ChatMessage);
	        this.placeholder = source["placeholder"];
	        this.originReviewId = source["originReviewId"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class Settings {
	    hub_url: string;
	    api_token?: string;
	    aggregators?: Record<string, AggregatorConfig>;
	    accounting_services?: Record<string, AccountingConfig>;
	    default_aggregator?: string;
	    default_accounting?: string;
	    timeout?: number;
	    endpoints_path?: string;
	    is_configured?: boolean;
	    marketplace_url?: string;
	    log_level?: string;
	    python_path?: string;
	    port?: number;
	    container_enabled?: boolean;
	    container_runtime?: string;
	    container_image?: string;
	    update_auto_check_enabled: boolean;
	    device_id?: string;

	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.hub_url = source["hub_url"];
	        this.api_token = source["api_token"];
	        this.aggregators = this.convertValues(source["aggregators"], AggregatorConfig, true);
	        this.accounting_services = this.convertValues(source["accounting_services"], AccountingConfig, true);
	        this.default_aggregator = source["default_aggregator"];
	        this.default_accounting = source["default_accounting"];
	        this.timeout = source["timeout"];
	        this.endpoints_path = source["endpoints_path"];
	        this.is_configured = source["is_configured"];
	        this.marketplace_url = source["marketplace_url"];
	        this.log_level = source["log_level"];
	        this.python_path = source["python_path"];
	        this.port = source["port"];
	        this.container_enabled = source["container_enabled"];
	        this.container_runtime = source["container_runtime"];
	        this.container_image = source["container_image"];
	        this.update_auto_check_enabled = source["update_auto_check_enabled"];
	        this.device_id = source["device_id"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}



	export class SkillInfo {
	    name: string;
	    title: string;
	    size: number;
	    modifiedAt: string;

	    static createFrom(source: any = {}) {
	        return new SkillInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.title = source["title"];
	        this.size = source["size"];
	        this.modifiedAt = source["modifiedAt"];
	    }
	}
	export class StatusInfo {
	    state: string;
	    errorMessage?: string;
	    mode: string;
	    uptime?: number;

	    static createFrom(source: any = {}) {
	        return new StatusInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.state = source["state"];
	        this.errorMessage = source["errorMessage"];
	        this.mode = source["mode"];
	        this.uptime = source["uptime"];
	    }
	}
	export class TransactionFilter {
	    endpoint_slug?: string;
	    status?: string;
	    since_unix?: number;
	    until_unix?: number;
	    limit?: number;

	    static createFrom(source: any = {}) {
	        return new TransactionFilter(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.endpoint_slug = source["endpoint_slug"];
	        this.status = source["status"];
	        this.since_unix = source["since_unix"];
	        this.until_unix = source["until_unix"];
	        this.limit = source["limit"];
	    }
	}
	export class TransactionPage {
	    records: PaymentRecord[];
	    total: number;
	    totals: PaymentTotals;

	    static createFrom(source: any = {}) {
	        return new TransactionPage(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.records = this.convertValues(source["records"], PaymentRecord);
	        this.total = source["total"];
	        this.totals = this.convertValues(source["totals"], PaymentTotals);
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}
	export class WalletBalance {
	    address: string;
	    amount: string;
	    currency: string;
	    decimals: number;
	    as_of_unix: number;

	    static createFrom(source: any = {}) {
	        return new WalletBalance(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.address = source["address"];
	        this.amount = source["amount"];
	        this.currency = source["currency"];
	        this.decimals = source["decimals"];
	        this.as_of_unix = source["as_of_unix"];
	    }
	}
	export class WalletInfo {
	    address: string;
	    chain_id: number;
	    rpc_url: string;
	    network: string;
	    key_exists: boolean;

	    static createFrom(source: any = {}) {
	        return new WalletInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.address = source["address"];
	        this.chain_id = source["chain_id"];
	        this.rpc_url = source["rpc_url"];
	        this.network = source["network"];
	        this.key_exists = source["key_exists"];
	    }
	}

	export class X402Receipt {
	    id: string;
	    payer: string;
	    pay_to: string;
	    amount: string;
	    currency: string;
	    chain_id: number;
	    nonce: number;
	    challenge_id: string;
	    status: string;
	    failure_reason?: string;
	    tx_hash?: string;
	    created_at: string;
	    settled_at?: string;

	    static createFrom(source: any = {}) {
	        return new X402Receipt(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.payer = source["payer"];
	        this.pay_to = source["pay_to"];
	        this.amount = source["amount"];
	        this.currency = source["currency"];
	        this.chain_id = source["chain_id"];
	        this.nonce = source["nonce"];
	        this.challenge_id = source["challenge_id"];
	        this.status = source["status"];
	        this.failure_reason = source["failure_reason"];
	        this.tx_hash = source["tx_hash"];
	        this.created_at = source["created_at"];
	        this.settled_at = source["settled_at"];
	    }
	}
	export class X402ReceiptFilter {
	    status?: string;
	    payer?: string;
	    limit?: number;

	    static createFrom(source: any = {}) {
	        return new X402ReceiptFilter(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.status = source["status"];
	        this.payer = source["payer"];
	        this.limit = source["limit"];
	    }
	}
	export class X402ReceiptPage {
	    records: X402Receipt[];
	    total: number;

	    static createFrom(source: any = {}) {
	        return new X402ReceiptPage(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.records = this.convertValues(source["records"], X402Receipt);
	        this.total = source["total"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}

export namespace manualreview {

	export class ResolvedEnvelope {
	    protocol: string;
	    type: string;
	    review_id: string;
	    session_id?: string;
	    endpoint_owner: string;
	    endpoint_slug: string;
	    endpoint_name?: string;
	    policy_name?: string;
	    sender_public_key: string;
	    nonce: string;
	    encrypted_payload: string;

	    static createFrom(source: any = {}) {
	        return new ResolvedEnvelope(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.protocol = source["protocol"];
	        this.type = source["type"];
	        this.review_id = source["review_id"];
	        this.session_id = source["session_id"];
	        this.endpoint_owner = source["endpoint_owner"];
	        this.endpoint_slug = source["endpoint_slug"];
	        this.endpoint_name = source["endpoint_name"];
	        this.policy_name = source["policy_name"];
	        this.sender_public_key = source["sender_public_key"];
	        this.nonce = source["nonce"];
	        this.encrypted_payload = source["encrypted_payload"];
	    }
	}
	export class ResolvedPayload {
	    review_id: string;
	    status: string;
	    resolved_at: string;
	    response_text?: string;
	    reject_reason?: string;
	    resolver_user_id?: string;

	    static createFrom(source: any = {}) {
	        return new ResolvedPayload(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.review_id = source["review_id"];
	        this.status = source["status"];
	        this.resolved_at = source["resolved_at"];
	        this.response_text = source["response_text"];
	        this.reject_reason = source["reject_reason"];
	        this.resolver_user_id = source["resolver_user_id"];
	    }
	}

}

export namespace updater {

	export class DownloadState {
	    stage: string;
	    version?: string;
	    bytes_done?: number;
	    bytes_total?: number;
	    local_path?: string;
	    error?: string;

	    static createFrom(source: any = {}) {
	        return new DownloadState(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.stage = source["stage"];
	        this.version = source["version"];
	        this.bytes_done = source["bytes_done"];
	        this.bytes_total = source["bytes_total"];
	        this.local_path = source["local_path"];
	        this.error = source["error"];
	    }
	}
	export class InstallState {
	    stage: string;
	    version?: string;
	    step?: string;
	    error?: string;

	    static createFrom(source: any = {}) {
	        return new InstallState(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.stage = source["stage"];
	        this.version = source["version"];
	        this.step = source["step"];
	        this.error = source["error"];
	    }
	}
	export class State {
	    stage: string;
	    current_version: string;
	    latest_version?: string;
	    min_supported_version?: string;
	    release_notes_url?: string;
	    must_update_reason?: string;
	    platform: string;
	    platform_supported: boolean;
	    download_size_bytes?: number;
	    // Go type: time
	    last_checked_at?: any;
	    last_error?: string;
	    auto_check_enabled: boolean;

	    static createFrom(source: any = {}) {
	        return new State(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.stage = source["stage"];
	        this.current_version = source["current_version"];
	        this.latest_version = source["latest_version"];
	        this.min_supported_version = source["min_supported_version"];
	        this.release_notes_url = source["release_notes_url"];
	        this.must_update_reason = source["must_update_reason"];
	        this.platform = source["platform"];
	        this.platform_supported = source["platform_supported"];
	        this.download_size_bytes = source["download_size_bytes"];
	        this.last_checked_at = this.convertValues(source["last_checked_at"], null);
	        this.last_error = source["last_error"];
	        this.auto_check_enabled = source["auto_check_enabled"];
	    }

		convertValues(a: any, classs: any, asMap: boolean = false): any {
		    if (!a) {
		        return a;
		    }
		    if (a.slice && a.map) {
		        return (a as any[]).map(elem => this.convertValues(elem, classs));
		    } else if ("object" === typeof a) {
		        if (asMap) {
		            for (const key of Object.keys(a)) {
		                a[key] = new classs(a[key]);
		            }
		            return a;
		        }
		        return new classs(a);
		    }
		    return a;
		}
	}

}
