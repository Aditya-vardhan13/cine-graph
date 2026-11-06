import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ segments: string[] }> };

function allowedPath(segments: string[]): string | null {
  if (segments.length === 1 && segments[0] === "queue") return "queue";
  if (segments.length === 1 && /^[0-9a-f-]{36}$/i.test(segments[0])) return segments[0];
  return null;
}

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const { segments } = await context.params;
  const path = allowedPath(segments);
  if (!path) return NextResponse.json({ detail: "Unknown rights review route" }, { status: 404 });
  const operatorEmail = process.env.CINEGRAPH_ADMIN_EMAIL;
  const internalToken = process.env.ADMIN_INTAKE_TOKEN;
  if (process.env.CINEGRAPH_LOCAL_ADMIN_MODE !== "1" ||
      process.env.CINEGRAPH_BIND_ADDRESS !== "127.0.0.1" ||
      !operatorEmail || !internalToken || internalToken.length < 24) {
    return NextResponse.json({ detail: "Local rights review is unavailable" }, { status: 503 });
  }
  if (request.headers.get("x-operator-email")?.trim().toLowerCase() !== operatorEmail.toLowerCase()) {
    return NextResponse.json({ detail: "Use the configured operator email" }, { status: 401 });
  }
  if ((path === "queue" && request.method !== "GET") ||
      (path !== "queue" && request.method !== "POST")) {
    return NextResponse.json({ detail: "Method not allowed" }, { status: 405 });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";
  try {
    const response = await fetch(`${base}/admin/rights/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers: {
        authorization: `Bearer ${internalToken}`,
        ...(request.method === "POST" ? { "content-type": "application/json" } : {}),
        "x-operator-email": operatorEmail,
      },
      body: request.method === "POST" ? await request.text() : undefined,
      cache: "no-store",
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json",
                 "cache-control": "no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "Local API is unavailable" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
