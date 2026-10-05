import { NextRequest, NextResponse } from "next/server";

type Context = { params: Promise<{ segments: string[] }> };

function upstreamPath(segments: string[]): string | null {
  if (segments.length === 1 && ["suggest", "jobs"].includes(segments[0])) return segments[0];
  if (segments.length === 3 && segments[0] === "jobs" && segments[2] === "retry" &&
      /^[0-9a-f-]{36}$/i.test(segments[1])) return segments.join("/");
  return null;
}

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const { segments } = await context.params;
  const path = upstreamPath(segments);
  if (!path) return NextResponse.json({ detail: "Unknown intake route" }, { status: 404 });
  const base = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";
  const url = `${base}/admin/intake/${path}${request.nextUrl.search}`;
  try {
    const response = await fetch(url, {
      method: request.method,
      headers: {
        authorization: request.headers.get("authorization") ?? "",
        ...(request.method === "POST" ? { "content-type": "application/json" } : {}),
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
