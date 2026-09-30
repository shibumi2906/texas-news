import type { Metadata } from "next";

import { SetupDashboard } from "@/components/setup-dashboard";

export const metadata: Metadata = {
  title: "Site setup",
  robots: { index: false, follow: false },
};

export default function SetupPage() {
  return <SetupDashboard />;
}
