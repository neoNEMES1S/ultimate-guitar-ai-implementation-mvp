import { NextResponse } from "next/server";

const icon = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#a5ec73"/>
  <path d="M17 32c0-9 7-16 16-16 5 0 9 2 12 6l-5 4c-2-2-4-3-7-3-5 0-9 4-9 9s4 9 9 9c3 0 6-1 8-4l5 4c-3 4-8 6-13 6-9 0-16-7-16-15Z" fill="#10131a"/>
</svg>`;

export function GET() {
  return new NextResponse(icon, {
    headers: {
      "Cache-Control": "public, max-age=86400",
      "Content-Type": "image/svg+xml",
    },
  });
}
