interface Env {
  VESSEL_ROUTES: KVNamespace;
  RATE_LIMITER: any;
  API_KEYS: KVNamespace;
}

interface VesselRoute {
  id: string;
  name: string;
  target: string;
  version: string;
  rateLimit: number;
  status: 'healthy' | 'degraded' | 'offline';
  lastChecked: number;
}

interface HealthStatus {
  gateway: 'healthy' | 'degraded';
  timestamp: number;
  vessels: Record<string, {
    status: 'healthy' | 'degraded' | 'offline';
    responseTime: number;
    lastChecked: number;
  }>;
}

const API_KEY_HEADER = 'X-API-Key';
const RATE_LIMIT_WINDOW = 60;
const MAX_REQUESTS_PER_MINUTE = 100;

const HTML_TEMPLATE = (content: string, title: string) => `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title} | Fleet API Gateway</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', sans-serif;
      background: #0a0a0f;
      color: #e2e8f0;
      line-height: 1.6;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .container {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0 20px;
      flex: 1;
    }
    header {
      padding: 2rem 0;
      border-bottom: 1px solid #1e1e2e;
      margin-bottom: 3rem;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 1.5rem;
      font-weight: 700;
      color: #fff;
    }
    .accent { color: #7c3aed; }
    .hero {
      text-align: center;
      padding: 3rem 0;
    }
    h1 {
      font-size: 3rem;
      font-weight: 700;
      margin-bottom: 1rem;
      background: linear-gradient(135deg, #7c3aed 0%, #c4b5fd 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .subtitle {
      font-size: 1.25rem;
      color: #94a3b8;
      max-width: 600px;
      margin: 0 auto 2rem;
    }
    .content {
      background: rgba(30, 30, 46, 0.5);
      border-radius: 12px;
      padding: 2rem;
      margin: 2rem 0;
      border: 1px solid #2d2d4d;
    }
    footer {
      margin-top: auto;
      padding: 2rem 0;
      border-top: 1px solid #1e1e2e;
      text-align: center;
      color: #64748b;
    }
    .fleet-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(124, 58, 237, 0.1);
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 0.875rem;
      margin-top: 1rem;
    }
    .status-healthy { color: #10b981; }
    .status-degraded { color: #f59e0b; }
    .status-offline { color: #ef4444; }
    code {
      background: rgba(0, 0, 0, 0.3);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: 'Courier New', monospace;
      font-size: 0.9em;
    }
    .endpoint {
      background: rgba(0, 0, 0, 0.2);
      padding: 1rem;
      border-radius: 8px;
      margin: 1rem 0;
      border-left: 4px solid #7c3aed;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="#7c3aed" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M2 17L12 22L22 17" stroke="#7c3aed" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M2 12L12 17L22 12" stroke="#7c3aed" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>Fleet <span class="accent">API Gateway</span></span>
      </div>
    </header>
    <main>
      <div class="hero">
        <h1>One URL, Every Vessel</h1>
        <p class="subtitle">Unified API gateway for all fleet vessel APIs with route-based proxying, rate limiting, authentication, and health monitoring.</p>
      </div>
      ${content}
    </main>
    <footer>
      <p>© ${new Date().getFullYear()} Fleet API Gateway. All vessel communications secured.</p>
      <div class="fleet-badge">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 15C13.6569 15 15 13.6569 15 12C15 10.3431 13.6569 9 12 9C10.3431 9 9 10.3431 9 12C9 13.6569 10.3431 15 12 15Z" fill="#7c3aed"/>
          <path d="M19 12C19 15.866 15.866 19 12 19C8.13401 19 5 15.866 5 12C5 8.13401 8.13401 5 12 5C15.866 5 19 8.13401 19 12Z" stroke="#7c3aed" stroke-width="2"/>
        </svg>
        <span>Fleet Network Active</span>
      </div>
    </footer>
  </div>
</body>
</html>`;

class RateLimiter {
  private limits: Map<string, { count: number; resetTime: number }> = new Map();

  async check(key: string, limit: number): Promise<{ allowed: boolean; remaining: number }> {
    const now = Math.floor(Date.now() / 1000);
    const windowKey = `${key}:${Math.floor(now / RATE_LIMIT_WINDOW)}`;
    
    let data = this.limits.get(windowKey);
    
    if (!data || now > data.resetTime) {
      data = { count: 0, resetTime: now + RATE_LIMIT_WINDOW };
      this.limits.set(windowKey, data);
    }
    
    if (data.count >= limit) {
      return { allowed: false, remaining: 0 };
    }
    
    data.count++;
    return { allowed: true, remaining: limit - data.count };
  }
}

async function authenticate(request: Request, env: Env): Promise<boolean> {
  const apiKey = request.headers.get(API_KEY_HEADER);
  if (!apiKey) return false;
  
  const validKey = await env.API_KEYS.get(apiKey);
  return validKey === 'active';
}

async function getVesselRoute(vesselId: string, env: Env): Promise<VesselRoute | null> {
  const route = await env.VESSEL_ROUTES.get(vesselId, 'json');
  return route as VesselRoute | null;
}

async function proxyRequest(request: Request, vesselRoute: VesselRoute, path: string): Promise<Response> {
  const targetUrl = new URL(path, vesselRoute.target);
  
  const proxyHeaders = new Headers(request.headers);
  proxyHeaders.set('X-Forwarded-For', request.headers.get('CF-Connecting-IP') || '');
  proxyHeaders.set('X-Vessel-ID', vesselRoute.id);
  proxyHeaders.set('X-Vessel-Version', vesselRoute.version);
  
  const proxyRequest = new Request(targetUrl.toString(), {
    method: request.method,
    headers: proxyHeaders,
    body: request.method !== 'GET' && request.method !== 'HEAD' ? request.body : undefined,
  });
  
  try {
    const response = await fetch(proxyRequest);
    const responseHeaders = new Headers(response.headers);
    responseHeaders.set('X-Gateway-Proxy', 'true');
    responseHeaders.set('X-Vessel-ID', vesselRoute.id);
    
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: 'Vessel unreachable', vessel: vesselRoute.id }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function updateVesselHealth(vesselId: string, env: Env, status: 'healthy' | 'degraded' | 'offline') {
  const route = await getVesselRoute(vesselId, env);
  if (route) {
    route.status = status;
    route.lastChecked = Date.now();
    await env.VESSEL_ROUTES.put(vesselId, JSON.stringify(route));
  }
}

async function checkVesselHealth(vesselRoute: VesselRoute): Promise<{ status: 'healthy' | 'degraded' | 'offline'; responseTime: number }> {
  const startTime = Date.now();
  try {
    const healthUrl = new URL('/health', vesselRoute.target);
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    
    const response = await fetch(healthUrl.toString(), {
      signal: controller.signal,
      headers: { 'User-Agent': 'Fleet-API-Gateway/1.0' },
    });
    
    clearTimeout(timeoutId);
    const responseTime = Date.now() - startTime;
    
    if (response.ok && responseTime < 1000) {
      return { status: 'healthy', responseTime };
    } else {
      return { status: 'degraded', responseTime };
    }
  } catch (error) {
    return { status: 'offline', responseTime: Date.now() - startTime };
  }
}

async function aggregateHealth(env: Env): Promise<HealthStatus> {
  const vessels: Record<string, any> = {};
  const allRoutes = await env.VESSEL_ROUTES.list();
  let allHealthy = true;
  
  for (const key of allRoutes.keys) {
    const route = await getVesselRoute(key.name, env);
    if (route) {
      const health = await checkVesselHealth(route);
      vessels[route.id] = {
        status: health.status,
        responseTime: health.responseTime,
        lastChecked: Date.now(),
      };
      
      await updateVesselHealth(route.id, env, health.status);
      
      if (health.status !== 'healthy') {
        allHealthy = false;
      }
    }
  }
  
  return {
    gateway: allHealthy ? 'healthy' : 'degraded',
    timestamp: Date.now(),
    vessels,
  };
}

function setSecurityHeaders(response: Response): Response {
  const headers = new Headers(response.headers);
  headers.set('X-Frame-Options', 'DENY');
  headers.set(
    'Content-Security-Policy',
    "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'"
  );
  headers.set('X-Content-Type-Options', 'nosniff');
  headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
const sh = {"Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; frame-ancestors 'none'","X-Frame-Options":"DENY"};
export default { async fetch(r: Request) { const u = new URL(r.url); if (u.pathname==='/health') return new Response(JSON.stringify({status:'ok'}),{headers:{'Content-Type':'application/json',...sh}}); return new Response(html,{headers:{'Content-Type':'text/html;charset=UTF-8',...sh}}); }};