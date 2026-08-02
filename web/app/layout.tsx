import "./styles.css";
import Script from "next/script";

export const metadata = { title: "Tab Verify", description: "AI-assisted tab review" };

export default function Layout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><Script src="https://apis.google.com/js/api.js" strategy="afterInteractive" /><Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" />{children}</body></html>;
}
