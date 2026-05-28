/**
 * Runtime API proxy — reads VYUHA_API_URL from process.env at server startup
 * (not baked at Docker build time like next.config env values).
 *
 * All client-side api.ts calls go to /api/proxy/... which this handler
 * forwards to the real upstream API.
 */

import { NextRequest, NextResponse } from "next/server";

const UPSTREAM = process.env.VYUHA_API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

// Headers that must not be forwarded to the upstream
const HOP_BY_HOP = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
]);

async function handler(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  try {
    const { path } = await params;
    const search = req.nextUrl.search;
    const url = `${UPSTREAM}/${path.join("/")}${search}`;

    // Forward headers, stripping hop-by-hop headers
    const forwardHeaders = new Headers();
    req.headers.forEach((value, key) => {
      if (!HOP_BY_HOP.has(key.toLowerCase())) {
        forwardHeaders.set(key, value);
      }
    });

    // Read body for non-GET/HEAD methods
    const body =
      req.method !== "GET" && req.method !== "HEAD"
        ? Buffer.from(await req.arrayBuffer())
        : undefined;

    const upstream = await fetch(url, {
      method: req.method,
      headers: forwardHeaders,
      body,
    });

    // Buffer the response to avoid streaming issues
    const responseBody = await upstream.arrayBuffer();

    // Only forward safe response headers
    const responseHeaders = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) responseHeaders.set("content-type", contentType);
    const contentLength = upstream.headers.get("content-length");
    if (contentLength) responseHeaders.set("content-length", contentLength);

    return new NextResponse(responseBody, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (err) {
    console.error("[proxy] error:", err);
    return NextResponse.json(
      { error: "Proxy error", detail: String(err) },
      { status: 502 }
    );
  }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
export const OPTIONS = handler;
