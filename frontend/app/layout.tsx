import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Customs Clearance",
  description: "Autonomous customs clearance demo — synthetic data only",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
