export namespace main {

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
	    policiesVersion: string;

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
	        this.policiesVersion = source["policiesVersion"];
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
	export class LogMessage {
	    role: string;
	    content: string;

	    static createFrom(source: any = {}) {
	        return new LogMessage(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.role = source["role"];
	        this.content = source["content"];
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
	    messages?: LogMessage[];
	    query?: string;
	    rawSize: number;

	    static createFrom(source: any = {}) {
	        return new LogRequestInfo(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.type = source["type"];
	        this.messages = this.convertValues(source["messages"], LogMessage);
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


	export class NewPolicyRequest {
	    name: string;
	    type: string;
	    childPolicies: string[];
	    denyReason: string;

	    static createFrom(source: any = {}) {
	        return new NewPolicyRequest(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.name = source["name"];
	        this.type = source["type"];
	        this.childPolicies = source["childPolicies"];
	        this.denyReason = source["denyReason"];
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

	export class Settings {
	    syfthubUrl: string;
	    apiKey?: string;
	    endpointsPath: string;
	    isConfigured: boolean;

	    static createFrom(source: any = {}) {
	        return new Settings(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.syfthubUrl = source["syfthubUrl"];
	        this.apiKey = source["apiKey"];
	        this.endpointsPath = source["endpointsPath"];
	        this.isConfigured = source["isConfigured"];
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
	export class UserAggregator {
	    id: number;
	    name: string;
	    url: string;
	    is_default: boolean;
	    created_at: string;

	    static createFrom(source: any = {}) {
	        return new UserAggregator(source);
	    }

	    constructor(source: any = {}) {
	        if ('string' === typeof source) source = JSON.parse(source);
	        this.id = source["id"];
	        this.name = source["name"];
	        this.url = source["url"];
	        this.is_default = source["is_default"];
	        this.created_at = source["created_at"];
	    }
	}

}
